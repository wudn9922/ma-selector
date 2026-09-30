"""純診斷：只比較「最後選擇規則」。不修改 production、gap、structural score、events_v22。
固定：gap=15、彼此差>2、最多 5 條、同一批候選、同一份 events_v22 反手報酬、同一份結構分數（平滑後、未四捨五入）。
A CURRENT           ：SAR ≥ best_SAR − 5pp → 取 period 最小（＝目前 production 規則）
B STRUCTURAL_TIEBREAK：SAR ≥ best_SAR − 5pp → 取結構分數最高（完全相同才取較短）
C STRUCTURAL_FIRST  ：結構分數 ≥ 最高結構分 − 3 → 取 SAR 最高；SAR 差 ≤5pp 者取結構分數較高（不預設取最短）
用法：python scripts/final_rule_experiment.py [--asof 2026-09-24] [--out experiments/final_rules] [--synthetic] [--only A,B]"""
import argparse, math, os, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R
from core import data, score, select as sel
from core.universe import TICKERS

GAP, PP, STRUCT = 15, 0.05, 3.0
RULES = ('A_CURRENT', 'B_STRUCTURAL_TIEBREAK', 'C_STRUCTURAL_FIRST')
NAMED = ['SMCI', 'LMT', 'DIS', 'GS', 'TSLA', 'ACN', 'ROST', 'NVO', 'ALSN', 'BB', 'NOK']

def pick(rule, cands):
    """cands：list of dict(period, s＝結構分, r＝SAR 報酬)，回傳選中的 period"""
    if rule == 'A_CURRENT':
        best = max(c['r'] for c in cands); return min((c for c in cands if c['r'] >= best - PP), key=lambda c: c['period'])['period']
    if rule == 'B_STRUCTURAL_TIEBREAK':
        best = max(c['r'] for c in cands); pool = [c for c in cands if c['r'] >= best - PP]
        return min(pool, key=lambda c: (-c['s'], c['period']))['period']
    bs = max(c['s'] for c in cands); pool = [c for c in cands if c['s'] >= bs - STRUCT]; br = max(c['r'] for c in pool)
    return min([c for c in pool if c['r'] >= br - PP], key=lambda c: (-c['s'], c['period']))['period']

def dist(f, us): return min(abs(f - u) for u in us)
def sign_p(k_s, k_l):
    n = k_s + k_l
    if n == 0: return np.nan
    m = min(k_s, k_l); return min(1., 2 * sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='experiments/final_rules'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='frwork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True); os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: newM = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in newM.items()], ignore_index=True); dfs = {tk: data.normalize(pd.read_csv(f'data_v/{tk}.csv'), a.asof) for tk in tks}
    cands, prod_final, bt_sets, sets_bad, prod_bad = {}, {}, {}, [], []
    for tk in tks:
        Sx = score.score_table(newM[tk], ref); P_, Ss = sel.smoothed_scores(Sx); sm = dict(zip(P_, Ss))
        r_sar = sel.select(dfs[tk], Sx, gap=GAP, method='sar', final_rule='min_period')['短期']; r_bt = sel.select(dfs[tk], Sx, gap=GAP, method='bt', longonly=True)['短期']
        cands[tk] = [dict(period=c['均線'], s=float(sm[c['均線']]), r=c['反手報酬'], n=c['反手筆數']) for c in r_sar['cands']]; prod_final[tk] = r_sar['final']
        if [c['均線'] for c in r_sar['cands']] != [c['均線'] for c in r_bt['cands']]: sets_bad.append(tk)
    print('候選完成', flush=True)
    user = {tk: [p for p in ps if p <= 33] for tk, ps in R.USER.items()}; gt = [tk for tk in tks if user.get(tk)]
    F = {r: {tk: pick(r, cands[tk]) for tk in tks} for r in RULES}
    prod_bad = [tk for tk in tks if F['A_CURRENT'][tk] != prod_final[tk]]        # 規則 A 必須與 production 的 final 逐檔相同
    struct_best = {tk: max(cands[tk], key=lambda c: (c['s'], -c['period']))['period'] for tk in tks}
    # ── 每檔每規則 ──
    rows = []
    for tk in tks:
        row = dict(ticker=tk, user_MAs=' '.join(map(str, user.get(tk, []))), candidates=' '.join(f"{c['period']}(s{c['s']:.2f},r{c['r']*100:+.1f}%,n{c['n']})" for c in cands[tk]), structural_best=struct_best[tk])
        for r in RULES:
            row[f'{r}_final'] = F[r][tk]; row[f'{r}_distance'] = dist(F[r][tk], user[tk]) if user.get(tk) else ''
        rows.append(row)
    T = pd.DataFrame(rows); T.to_csv(out / 'rules_per_ticker.csv', index=False)
    # ── 統計 ──
    hits, shifts = [], []
    for r in RULES:
        d = np.array([dist(F[r][tk], user[tk]) for tk in gt]); base = np.array([dist(F['A_CURRENT'][tk], user[tk]) for tk in gt])
        hits.append(dict(rule=r, exact=int((d == 0).sum()), pm1=int((d <= 1).sum()), pm2=int((d <= 2).sum()), pm3=int((d <= 3).sum()), n=len(gt), mean_distance=round(float(d.mean()), 3), median_distance=float(np.median(d)),
                         frac_le2=round(float((d <= 2).mean()), 3), frac_gt5=round(float((d > 5).mean()), 3), improved_vs_A=int((d < base).sum()), same_vs_A=int((d == base).sum()), worsened_vs_A=int((d > base).sum()),
                         final_changed_vs_A=int(sum(F[r][tk] != F['A_CURRENT'][tk] for tk in gt))))
        for scope, ids in (('61 labelled', gt), ('all', tks)):
            sh = np.array([F[r][tk] - struct_best[tk] for tk in ids]); ks, ke, kl = int((sh < 0).sum()), int((sh == 0).sum()), int((sh > 0).sum())
            shifts.append(dict(rule=r, scope=scope, n=len(ids), shorter=ks, same=ke, longer=kl, mean_shift=round(float(sh.mean()), 2), median_shift=float(np.median(sh)), sign_test_p=round(sign_p(ks, kl), 4)))
    H = pd.DataFrame(hits); H.to_csv(out / 'rules_hits.csv', index=False); Sh = pd.DataFrame(shifts); Sh.to_csv(out / 'rules_shift_stats.csv', index=False)
    named = []
    for tk in NAMED:
        if tk in tks: named.append(dict(ticker=tk, **{k: T[T.ticker == tk].iloc[0][k] for k in ('user_MAs', 'structural_best', 'candidates')}, **{f'{r}': f"{F[r][tk]} (d={dist(F[r][tk], user[tk]) if user.get(tk) else '-'})" for r in RULES}))
    N_ = pd.DataFrame(named); N_.to_csv(out / 'rules_named.csv', index=False)
    # ── 報告 ──
    L = []; P = lambda *x: L.append(' '.join(str(i) for i in x))
    P(f'# 最後選擇規則診斷（gap={GAP}，SAR 差距 {PP*100:.0f}pp，結構分容許 {STRUCT} 分；asof {a.asof}；{len(tks)} 檔，{len(gt)} 檔有短期人工標記）\n')
    P('只比較最後選擇規則；候選、events_v22 反手報酬、結構分數完全固定。**未修改 production。**\n')
    P(f'- 候選集合在三個規則之間相同（同一份候選清單套用三條規則）：是；反手與只做多兩種回測所得候選是否相同：{"是" if not sets_bad else "**否 → implementation bug：" + str(sets_bad) + "**"}')
    P(f'- 規則 A 與 production 的 final 逐檔相同：{"是" if not prod_bad else "**否 → implementation bug：" + str(prod_bad) + "**"}\n')
    P('## 1. 61 檔人工 ground truth\n\n| 規則 | exact | ±1 | ±2 | ±3 | 平均距離 | 中位數 | 距離≤2 比例 | 距離>5 比例 | 對 A：進步/相同/退步 | final 與 A 不同 |\n|---|---|---|---|---|---|---|---|---|---|---|')
    for h in H.itertuples(): P(f'| {h.rule} | {h.exact}/{h.n} | {h.pm1}/{h.n} | {h.pm2}/{h.n} | {h.pm3}/{h.n} | {h.mean_distance} | {h.median_distance} | {h.frac_le2:.0%} | {h.frac_gt5:.0%} | {h.improved_vs_A}/{h.same_vs_A}/{h.worsened_vs_A} | {h.final_changed_vs_A} |')
    P('\n## 2. 相對結構分第一名的 period 移動（final − structural_best）\n\n| 規則 | 範圍 | n | 更短 | 相同 | 更長 | 平均 | 中位數 | 符號檢定 p |\n|---|---|---|---|---|---|---|---|---|')
    for s in Sh.itertuples(): P(f'| {s.rule} | {s.scope} | {s.n} | {s.shorter} | {s.same} | {s.longer} | {s.mean_shift} | {s.median_shift} | {s.sign_test_p} |')
    P('\n## 3. 指定股票（d＝到最近人工 MA 的距離）\n\n| 股票 | 人工 | 結構分第一 | A CURRENT | B STRUCT_TIEBREAK | C STRUCT_FIRST | 候選（s＝結構分，r＝反手報酬，n＝筆數） |\n|---|---|---|---|---|---|---|')
    for r in named: P(f"| {r['ticker']} | {r['user_MAs']} | {r['structural_best']} | {r['A_CURRENT']} | {r['B_STRUCTURAL_TIEBREAK']} | {r['C_STRUCTURAL_FIRST']} | {r['candidates']} |")
    if fails: P('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'rules_report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
