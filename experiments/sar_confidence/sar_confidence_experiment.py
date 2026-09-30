"""純診斷（不改 production）：SAR confidence-aware finalist 實驗。
固定：候選產生（gap=15、間距>2、最多 5 條）、結構分數、events_v22 SAR lifecycle。只比較「finalist 的判定方式」。
  CURRENT_RULE_B        ：SAR ≥ best_SAR − 5pp → 取未四捨五入結構分最高（完全相同才取較短）＝ production
  CA95_L10 / CA90_L10   ：paired circular moving-block bootstrap（區塊長 10；20,000 次；seed 20260930）。
                          每次重抽：R[j,b]=Π(1+r)−1；BEST[b]=max_j R[j,b]（每次重算，不是觀察到的冠軍）；GAP[j,b]=BEST[b]−R[j,b]。
                          若 P(GAP[j]>5pp) ≥ 95%（CA90 為 90%）→ 剔除候選 j；觀察到 SAR 最高者一律保留；之後同規則 B 取結構分最高。
  CA95_L5 / CA95_L20    ：區塊長度敏感度（不得事後挑最好的）
  POSTHOC_10PT_10PP_RESCUE：事後對照，**POST-HOC / NOT ELIGIBLE FOR DIRECT PRODUCTION ADOPTION**
用法：python experiments/sar_confidence/sar_confidence_experiment.py [--asof 2026-09-24] [--out experiments/sar_confidence] [--synthetic] [--reps 20000]"""
import argparse, math, os, sys, tempfile, zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
from core import data, events as ev, score, select as sel

SEED = 20260930; REPS = 20000; GT_REPS = 10000; W = 252; GAP = 15
PP = 0.05                                   # production 的 5pp
BLOCKS = (10, 5, 20)                        # 10＝primary；5／20＝敏感度
VARIANTS = ('CURRENT_RULE_B', 'CA95_L10', 'CA90_L10', 'CA95_L5', 'CA95_L20', 'POSTHOC_10PT_10PP_RESCUE')
CA_SPEC = {'CA95_L10': (10, 95), 'CA90_L10': (10, 90), 'CA95_L5': (5, 95), 'CA95_L20': (20, 95)}
NAMED = ['SMCI', 'LMT', 'DIS', 'GS', 'TSLA', 'ACN', 'ROST', 'NVO', 'ALSN', 'BB', 'NOK', 'TSM', 'TMO', 'ODFL']
POSTHOC_LABEL = 'POST-HOC / NOT ELIGIBLE FOR DIRECT PRODUCTION ADOPTION'
TOL = 1e-12
# 外部壓力案例（只有摘要表，沒有日資料；僅質化用，不得拿來調參）：MA → (結構分, SAR 報酬, 筆數)
EXTERNAL = {29: (59.9, 0.764, 18), 16: (52.4, 0.395, 31), 32: (48.1, 0.534, 21), 26: (47.7, 0.337, 25), 19: (46.5, 0.815, 23)}

# ───────── SAR 逐日報酬重建（依 core.select.sar_stats 的邏輯；不修改 core） ─────────
def sar_daily_returns(O, H, L, C, atr, ma, lo):
    """回傳 (逐日報酬 r[lo:N]、逐日盤後市值 eq[lo:N]、複利總報酬)。
    市值＝視窗內（出場日 ≥ lo）各筆交易依序複利；持倉中按收盤估值（進場價 ep 來自 events_v22 的 plog）。r[t]=eq[t]/eq[t−1]−1，eq[lo−1]≡1。"""
    N = len(C); _b, _w, _r, plog, trades = ev.events(O, H, L, C, ma, atr)
    ep = {(a, b, sg): e for a, b, sg, e, _x, _k in plog}; tr = sorted([t for t in trades if t[1] >= lo], key=lambda t: (t[0], t[1]))
    eq = np.ones(N); cap = 1.
    for tin, tout, sg, r, _k in tr:
        e = ep.get((tin, tout, sg))
        if e is not None:
            for t in range(max(tin, lo), tout): eq[t] = cap * (1 + sg * (C[t] / e - 1))
        cap *= (1 + r); eq[max(tout, lo):] = cap
    seg = np.r_[1., eq[lo:]]; rets = seg[1:] / seg[:-1] - 1
    return rets, eq[lo:], float(cap - 1)

def compound(rets): return float(np.prod(1 + np.asarray(rets, float)) - 1)

# ───────── paired circular moving-block bootstrap ─────────
def indices_from_starts(starts, n, L):
    """starts：(reps, nb) 區塊起點。每列＝nb 個長度 L 的循環連續區塊（index mod n）串接後截成 n。"""
    reps, nb = starts.shape; idx = (starts[:, :, None] + np.arange(L)[None, None, :]) % n
    return idx.reshape(reps, nb * L)[:, :n]

def block_indices(n, L, reps, rng):
    nb = -(-n // L); return indices_from_starts(rng.integers(0, n, size=(reps, nb)), n, L)

def bootstrap_R(rets_mat, idx):
    """rets_mat：(k, n) 各候選的逐日報酬（同一交易日對齊）；idx：(reps, n)。所有候選共用同一份 idx。回傳 R：(k, reps)。"""
    X = 1 + np.asarray(rets_mat, float); out = np.empty((X.shape[0], idx.shape[0]))
    for j in range(X.shape[0]): out[j] = np.prod(X[j][idx], axis=1) - 1
    return out

def gap_stats(rets_mat, L, reps, rng, chunk=2000, pp=PP):
    """回傳 dict：count_gap（每個候選 GAP>pp 的次數，整數）、count_best（該次重抽中為最高者的次數；並列全計）、reps。BEST 每次重抽重算。"""
    k, n = np.asarray(rets_mat).shape; nb = -(-n // L); starts = rng.integers(0, n, size=(reps, nb)); cg = np.zeros(k, int); cb = np.zeros(k, int)
    for a in range(0, reps, chunk):
        idx = indices_from_starts(starts[a:a + chunk], n, L)
        R = bootstrap_R(rets_mat, idx); BEST = R.max(axis=0); GAP = BEST[None, :] - R
        cg += (GAP > pp).sum(axis=1); cb += (R >= BEST[None, :]).sum(axis=1)
    return dict(count_gap=cg, count_best=cb, reps=reps)

# ───────── finalist / final 規則 ─────────
def struct_best(cands): return max(cands, key=lambda c: (c['s'], -c['period']))['period']
def finalists_rule_b(cands):
    best = max(c['r'] for c in cands); return [c['period'] for c in cands if c['r'] >= best - PP]
def final_from(cands, fin):
    return min((c for c in cands if c['period'] in fin), key=lambda c: (-c['s'], c['period']))['period']     # 未四捨五入結構分最高；完全相同才取較短
def pick_rule_b(cands): return final_from(cands, finalists_rule_b(cands))

def survives(count, reps, thr_pct):
    """整數運算的邊界：P(GAP>5pp) = count/reps ≥ thr_pct% → 剔除（含等號）。"""
    return not (count * 100 >= thr_pct * reps)
def finalists_ca(cands, count_gap, reps, thr_pct):
    best = max(c['r'] for c in cands)
    return [c['period'] for c, cg in zip(cands, count_gap) if c['r'] == best or survives(int(cg), reps, thr_pct)]
def pick_ca(cands, count_gap, reps, thr_pct): return final_from(cands, finalists_ca(cands, count_gap, reps, thr_pct))

def pick_posthoc(cands, struct_pts=10.0, sar_pp=0.10):
    """事後對照：結構分第一名被 5pp 門檻剔除，且結構分 ≥ 規則 B final + 10.0，且觀察 SAR 差距 ≤ 10pp → 救回結構分第一名。"""
    f0 = pick_rule_b(cands); best = max(c['r'] for c in cands); sb = struct_best(cands)
    cs = {c['period']: c for c in cands}
    if sb != f0 and sb not in finalists_rule_b(cands) and cs[sb]['s'] >= cs[f0]['s'] + struct_pts and cs[sb]['r'] >= best - sar_pp: return sb
    return f0

# ───────── 統計 ─────────
def dist(f, us): return min(abs(f - u) for u in us)
def sign_p(k_s, k_l):
    n = k_s + k_l
    if n == 0: return float('nan')
    m = min(k_s, k_l); return min(1., 2 * sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n)
def mcnemar_exact(b, c):
    """b＝miss→hit（進步）、c＝hit→miss（退步）；雙尾 exact binomial（p=0.5）。沒有不一致對時 p=1（不是「證明相同」）。"""
    n = b + c
    if n == 0: return 1.0
    m = min(b, c); return min(1., 2 * sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n)
def paired_boot_mean_diff(diff, reps=GT_REPS, seed=SEED):
    diff = np.asarray(diff, float); rng = np.random.default_rng(seed); n = len(diff)
    m = diff[rng.integers(0, n, size=(reps, n))].mean(axis=1); return float(diff.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))

# ───────── 主流程 ─────────
def fmt_cands(cands): return ' '.join(f"{c['period']}(s{c['s']:.2f},r{c['r']*100:+.1f}%,n{c['n']})" for c in cands)
def fmt_p(cands, cnt, reps): return ' '.join(f"{c['period']}:{int(g) / reps:.3f}" for c, g in zip(cands, cnt))

def write_blocked(out, status, lines):
    (out / 'sar_confidence_report.md').write_text(f'# SAR confidence-aware finalist 診斷\n\n**STATUS = {status}**\n\n' + '\n'.join(lines) + '\n', encoding='utf-8'); print(status); print('\n'.join(lines))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='experiments/sar_confidence'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); ap.add_argument('--reps', type=int, default=REPS); ap.add_argument('--gt-reps', type=int, default=GT_REPS)
    ap.add_argument('--frozen', default=str(ROOT / 'experiments/final_rules/rules_per_ticker.csv')); a = ap.parse_args()
    import regression as R
    from core.universe import TICKERS
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); frozen = Path(a.frozen).resolve()
    wd = Path(a.work or tempfile.mkdtemp(prefix='sarcwork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True)
    if fails and not a.synthetic: write_blocked(out, 'DATA_FETCH_FAILURE', [f'- {t}: {e}' for t, e in fails]); sys.exit(2)
    os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: newM = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in newM.items()], ignore_index=True); dfs = {tk: data.normalize(pd.read_csv(f'data_v/{tk}.csv'), a.asof) for tk in tks}
    # ── 候選（production 設定；final_rule 只影響 final，候選相同）──
    cands, prod_final, arrs = {}, {}, {}
    for tk in tks:
        Sx = score.score_table(newM[tk], ref); P_, Ss = sel.smoothed_scores(Sx); sm = dict(zip(P_, Ss)); df = dfs[tk]
        r = sel.select(df, Sx, gap=GAP, method='sar')['短期']                                                   # production 規則 B
        cands[tk] = [dict(period=c['均線'], s=float(c['結構分']), r=c['反手報酬'], n=c['反手筆數'], mdd=c['反手回撤']) for c in r['cands']]; prod_final[tk] = r['final']
        assert all(c['s'] == float(sm[c['period']]) for c in cands[tk])
        arrs[tk] = tuple(df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')) + (data.wilder_atr(df), df.close)
    print('候選完成', flush=True)
    # ── Gate 1：候選集合必須與 rules_per_ticker.csv 完全相同 ──
    fz = pd.read_csv(frozen, dtype=str, keep_default_na=False).set_index('ticker'); mism = []
    if not a.synthetic:
        if set(fz.index) != set(tks): mism.append(f'ticker 集合不同：只在 CSV {sorted(set(fz.index) - set(tks))}；只在本次 {sorted(set(tks) - set(fz.index))}')
        for tk in tks:
            if tk in fz.index:
                mine, theirs = fmt_cands(cands[tk]), fz.loc[tk, 'candidates']
                if mine != theirs: mism.append(f'{tk}: 本次 [{mine}] ≠ 凍結 [{theirs}]')
        if mism: write_blocked(out, 'BLOCKED_CANDIDATE_MISMATCH', [f'- {m}' for m in mism]); sys.exit(3)
    cand_match = 'SYNTHETIC（不比對）' if a.synthetic else f'YES（{len(tks)}/{len(tks)} 檔，週期、結構分、SAR 報酬、筆數逐檔完全相同）'
    # ── Gate 2：SAR 逐日重建 vs production sar_stats ──
    rec, recon_bad = [], []
    daily = {}
    for tk in tks:
        O, H, L, C, atr, close = arrs[tk]; N = len(C); lo = max(N - W, 0); rows = []
        for c in cands[tk]:
            ma = close.rolling(c['period']).mean().to_numpy(); rets, eq, tot = sar_daily_returns(O, H, L, C, atr, ma, lo)
            prod = sel.sar_stats(O, H, L, C, atr, ma, lo)['報酬']; comp = compound(rets); d = abs(comp - prod)
            rec.append(dict(ticker=tk, period=c['period'], production=prod, select_value=c['r'], reconstructed=comp, abs_diff=d)); rows.append(rets)
            if not (d <= TOL) or abs(prod - c['r']) > 0: recon_bad.append(f"{tk} MA{c['period']}: production {prod!r} vs 重建 {comp!r} 差 {d:.3e}（select {c['r']!r}）")
        daily[tk] = np.array(rows)
    Rec = pd.DataFrame(rec); Rec.to_csv(out / 'sar_confidence_reconstruction.csv', index=False)
    if recon_bad: write_blocked(out, 'BLOCKED_SAR_RECONSTRUCTION_MISMATCH', [f'- {m}' for m in recon_bad]); sys.exit(4)
    maxdiff = float(Rec.abs_diff.max()); recon_txt = f'PASS（{len(Rec)} 個候選、{len(tks)} 檔；最大絕對差 {maxdiff:.3e} ≤ 1e-12）'; print('SAR 重建', recon_txt, flush=True)
    # ── bootstrap（每檔用 seed=20260930 ＋ ticker crc32 的獨立串流；同一檔所有候選共用同一批區塊）──
    reps = a.reps; boot = {L: {} for L in BLOCKS}
    for tk in tks:
        for L in BLOCKS:
            rng = np.random.default_rng([SEED, zlib.crc32(tk.encode())]); boot[L][tk] = gap_stats(daily[tk], L, reps, rng)
    print('bootstrap 完成', flush=True)
    # ── 各規則 final ──
    F = {v: {} for v in VARIANTS}; FIN = {v: {} for v in VARIANTS if v != 'POSTHOC_10PT_10PP_RESCUE'}
    for tk in tks:
        cs = cands[tk]; F['CURRENT_RULE_B'][tk] = pick_rule_b(cs); FIN['CURRENT_RULE_B'][tk] = finalists_rule_b(cs)
        for v, (L, thr) in CA_SPEC.items():
            fin = finalists_ca(cs, boot[L][tk]['count_gap'], reps, thr); FIN[v][tk] = fin; F[v][tk] = final_from(cs, fin)
        F['POSTHOC_10PT_10PP_RESCUE'][tk] = pick_posthoc(cs)
    bad_prod = [tk for tk in tks if F['CURRENT_RULE_B'][tk] != prod_final[tk]]
    if bad_prod: write_blocked(out, 'BLOCKED_RULE_B_MISMATCH', [f'- {tk}: 診斷 {F["CURRENT_RULE_B"][tk]} ≠ production {prod_final[tk]}' for tk in bad_prod]); sys.exit(5)
    sb = {tk: struct_best(cands[tk]) for tk in tks}
    user = {tk: [p for p in ps if p <= 33] for tk, ps in R.USER.items()}; gt = [tk for tk in tks if user.get(tk)]
    # ── per ticker ──
    rows = []
    for tk in tks:
        row = dict(ticker=tk, user_MAs=' '.join(map(str, user.get(tk, []))), candidates=fmt_cands(cands[tk]), n_candidates=len(cands[tk]), structural_best=sb[tk])
        for v in VARIANTS:
            row[f'{v}_final'] = F[v][tk]
            if v in FIN: row[f'{v}_finalists'] = ' '.join(map(str, FIN[v][tk])); row[f'{v}_n_finalists'] = len(FIN[v][tk])
            row[f'{v}_distance'] = dist(F[v][tk], user[tk]) if user.get(tk) else ''
        for L in BLOCKS:
            row[f'P_gap_gt5pp_L{L}'] = fmt_p(cands[tk], boot[L][tk]['count_gap'], reps); row[f'P_bootstrap_best_L{L}'] = fmt_p(cands[tk], boot[L][tk]['count_best'], reps)
        rows.append(row)
    T = pd.DataFrame(rows); T.to_csv(out / 'sar_confidence_per_ticker.csv', index=False)
    # ── 統計 ──
    summ, gtrows = [], {}
    for v in VARIANTS:
        d = np.array([dist(F[v][tk], user[tk]) for tk in gt]); base = np.array([dist(F['CURRENT_RULE_B'][tk], user[tk]) for tk in gt])
        imp, sam, wor = int((d < base).sum()), int((d == base).sum()), int((d > base).sum())
        hit_new, hit_cur = d <= 2, base <= 2; b = int((~hit_cur & hit_new).sum()); c_ = int((hit_cur & ~hit_new).sum())
        m, lo_, hi_ = paired_boot_mean_diff(d - base, a.gt_reps)
        gtrows[v] = dict(exact=int((d == 0).sum()), pm1=int((d <= 1).sum()), pm2=int((d <= 2).sum()), pm3=int((d <= 3).sum()), n=len(gt), mean_distance=float(d.mean()), median_distance=float(np.median(d)), gt5=int((d > 5).sum()),
                         improved=imp, same=sam, worsened=wor, changed=int(sum(F[v][tk] != F['CURRENT_RULE_B'][tk] for tk in gt)), mean_diff=m, ci_lo=lo_, ci_hi=hi_, miss_to_hit=b, hit_to_miss=c_, mcnemar_p=mcnemar_exact(b, c_))
        for scope, ids in ((f'labelled ({len(gt)})', gt), (f'all ({len(tks)})', tks)):
            sh = np.array([F[v][tk] - sb[tk] for tk in ids]); ks, ke, kl = int((sh < 0).sum()), int((sh == 0).sum()), int((sh > 0).sum())
            r_ = dict(variant=v, scope=scope, n=len(ids), shorter=ks, same=ke, longer=kl, mean_shift=float(sh.mean()), median_shift=float(np.median(sh)), sign_test_p=sign_p(ks, kl))
            if v in FIN:
                fc = np.array([len(FIN[v][tk]) for tk in ids]); r_.update(mean_finalists=float(fc.mean()), median_finalists=float(np.median(fc)), all_survive=int(sum(len(FIN[v][tk]) == len(cands[tk]) for tk in ids)),
                                                                          all_survive_multi=int(sum(len(FIN[v][tk]) == len(cands[tk]) and len(cands[tk]) > 1 for tk in ids)), multi_cand=int(sum(len(cands[tk]) > 1 for tk in ids)))
            if scope.startswith('labelled'): r_.update(gtrows[v])
            summ.append(r_)
    Sm = pd.DataFrame(summ); Sm.to_csv(out / 'sar_confidence_summary.csv', index=False)
    # ── 指定股票 ──
    named = []
    for tk in NAMED:
        if tk not in tks: continue
        cs = cands[tk]; ds = lambda v: f"{F[v][tk]} (d={dist(F[v][tk], user[tk]) if user.get(tk) else '-'})"
        named.append(dict(ticker=tk, user_MAs=' '.join(map(str, user.get(tk, []))), structural_best=sb[tk],
                          candidates_s_r_n_P10=' '.join(f"{c['period']}(s{c['s']:.2f},r{c['r']*100:+.1f}%,n{c['n']},P>5pp={boot[10][tk]['count_gap'][i] / reps:.3f})" for i, c in enumerate(cs)),
                          **{v: ds(v) for v in VARIANTS}, P_gap_gt5pp_L5=fmt_p(cs, boot[5][tk]['count_gap'], reps), P_gap_gt5pp_L20=fmt_p(cs, boot[20][tk]['count_gap'], reps)))
    N_ = pd.DataFrame(named); N_.to_csv(out / 'sar_confidence_named.csv', index=False)
    # ── 外部壓力案例（摘要表，不可評估 CA）──
    ex_c = [dict(period=p, s=v[0], r=v[1], n=v[2]) for p, v in EXTERNAL.items()]
    ext = dict(CURRENT_RULE_B=pick_rule_b(ex_c), POSTHOC_10PT_10PP_RESCUE=pick_posthoc(ex_c), CA95='NOT EVALUABLE FROM SUMMARY ONLY', CA90='NOT EVALUABLE FROM SUMMARY ONLY')
    pd.DataFrame([dict(MA=p, structural=v[0], SAR=v[1], trades=v[2]) for p, v in EXTERNAL.items()]).assign(**{k: x for k, x in ext.items()}).to_csv(out / 'sar_confidence_external_stress.csv', index=False)
    # ── 報告 ──
    Lr = []; P = lambda *x: Lr.append(' '.join(str(i) for i in x))
    P(f'# SAR confidence-aware finalist 診斷（**純診斷；PRODUCTION CHANGED = NO**）\n')
    P(f'asof {a.asof}｜{len(tks)} 檔開發集｜短期 SMA15–33、W={W}｜candidate gap={GAP}｜{len(gt)} 檔有短期人工標記｜{"**SYNTHETIC 資料（僅供流程測試，數字無意義）**" if a.synthetic else "真實資料"}\n')
    P(f'- CANDIDATE SET MATCH（對 experiments/final_rules/rules_per_ticker.csv）：{cand_match}')
    P(f'- SAR RECONSTRUCTION：{recon_txt}')
    P(f'- CURRENT_RULE_B 與 production `select()` final 逐檔相同：是（{len(tks)}/{len(tks)}）')
    P(f'- PRIMARY：block length 10，{reps} 次，seed {SEED}（每檔 seed 串流＝[{SEED}, crc32(ticker)]；同一檔所有候選、所有 block 長度共用同一 seed，候選共用同一批區塊）。敏感度：block 5／20（同次數同 seed，僅報告，不挑最佳）。')
    P(f'- CA95＝P(GAP>5pp) ≥ 95% 才剔除；CA90＝≥ 90%；觀察到 SAR 最高者一律保留；之後取未四捨五入結構分最高、完全相同取較短。門檻不調。')
    P(f'- POSTHOC_10PT_10PP_RESCUE：**{POSTHOC_LABEL}**（結構分第一被 5pp 門檻剔除、結構分 ≥ 規則 B final +10.0、觀察 SAR 差距 ≤10pp → 救回；10／10 不調）\n')
    G = lambda v: gtrows[v]
    P(f'## 1. {len(gt)} 檔人工 ground truth（距離＝到最近人工 MA）\n\n| 變體 | exact | ±1 | ±2 | ±3 | 平均距離 | 中位數 | 距離>5 | 對 CURRENT：進步/相同/退步 | final 與 CURRENT 不同 |\n|---|---|---|---|---|---|---|---|---|---|')
    for v in VARIANTS: g = G(v); P(f"| {v} | {g['exact']} | {g['pm1']} | {g['pm2']} | {g['pm3']} | {g['mean_distance']:.3f} | {g['median_distance']:.1f} | {g['gt5']} | {g['improved']}/{g['same']}/{g['worsened']} | {g['changed']} |")
    P(f'\n## 2. 配對統計（相對 CURRENT_RULE_B；ticker-level 配對；**p>0.05 不代表「相同」**）\n\n| 變體 | mean(新距離−舊距離) | 95% CI（bootstrap {a.gt_reps} 次，seed {SEED}） | ≤2：miss→hit | hit→miss | exact McNemar p |\n|---|---|---|---|---|---|')
    for v in VARIANTS[1:]: g = G(v); P(f"| {v} | {g['mean_diff']:+.3f} | [{g['ci_lo']:+.3f}, {g['ci_hi']:+.3f}] | {g['miss_to_hit']} | {g['hit_to_miss']} | {g['mcnemar_p']:.4f} |")
    P('\n## 3. 結構分偏移（final − structural_best）與 finalist 數\n\n| 變體 | 範圍 | n | 更短 | 相同 | 更長 | 平均 | 中位數 | 符號檢定 p | finalist 平均 | 中位數 | 全部候選都存活（含單一候選） | 其中候選≥2 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for s in summ:
        fin_ = f"{s['mean_finalists']:.2f} | {s['median_finalists']:.1f} | {s['all_survive']}/{s['n']} | {s['all_survive_multi']}/{s['multi_cand']}" if 'mean_finalists' in s else 'n/a | n/a | n/a | n/a'
        P(f"| {s['variant']} | {s['scope']} | {s['n']} | {s['shorter']} | {s['same']} | {s['longer']} | {s['mean_shift']:.2f} | {s['median_shift']:.1f} | {s['sign_test_p']:.4f} | {fin_} |")
    P('\n## 4. 指定股票（d＝到最近人工 MA 的距離；P10＝block 10 的 P(GAP>5pp)）\n\n| 股票 | 人工 | 結構分第一 | 候選（結構分,SAR,筆數,P10） | CURRENT | CA95_L10 | CA90_L10 | CA95_L5 | CA95_L20 | POSTHOC（事後） |\n|---|---|---|---|---|---|---|---|---|---|')
    for r in named: P(f"| {r['ticker']} | {r['user_MAs']} | {r['structural_best']} | {r['candidates_s_r_n_P10']} | {r['CURRENT_RULE_B']} | {r['CA95_L10']} | {r['CA90_L10']} | {r['CA95_L5']} | {r['CA95_L20']} | {r['POSTHOC_10PT_10PP_RESCUE']} |")
    P('\n## 5. 外部壓力案例（held-out、只有摘要表、質化用；不用來調參）\n\n| MA | 結構分 | SAR | 筆數 |\n|---|---|---|---|')
    for p, v in EXTERNAL.items(): P(f'| {p} | {v[0]} | {v[1]*100:+.1f}% | {v[2]} |')
    P(f"\n- CURRENT_RULE_B → {ext['CURRENT_RULE_B']}；POSTHOC_10PT_10PP_RESCUE → {ext['POSTHOC_10PT_10PP_RESCUE']}（{POSTHOC_LABEL}）；CA95 / CA90：**NOT EVALUABLE FROM SUMMARY ONLY**（沒有逐日序列，不可捏造）")
    P('\n> 統計證據、描述性結果、事後觀察必須分開解讀；見 `sar_confidence_interpretation.md`。\n')
    (out / 'sar_confidence_report.md').write_text('\n'.join(Lr), encoding='utf-8'); print('\n'.join(Lr))

if __name__ == '__main__': main()
