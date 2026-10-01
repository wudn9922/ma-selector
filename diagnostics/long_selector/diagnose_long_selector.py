"""NVO／TMO 長期（SMA46–110）selector 診斷：純診斷，不修改任何 production 檔案、規則或門檻。
沿用 scripts/production_sanity.py 的做法：ASOF 2026-09-24、83 檔資料、以這 83 檔自己的特徵分佈當基準（in-sample reference）、現行 main 的 core 程式。
對每檔輸出 SMA46–110 全部 65 條的原始 long metrics、score.py 實際使用的 transformed／percentile 成分、raw／平滑分數、與 best−15 的距離，
並逐步重播 core/select.py 的 candidate generation（排序 → gap → 間距 >2 → 最多 5 條）標出每條被選／淘汰的原因。
使用者人工答案只用來「標記圖上的位置」，不參與任何計算。
用法：python diagnostics/long_selector/diagnose_long_selector.py [--asof 2026-09-24] [--out diagnostics/long_selector] [--synthetic] [--only A,B]"""
import argparse, os, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R
from core import data, score, select as sel
from core.universe import TICKERS

TARGETS = {'NVO': 64, 'TMO': 85}                                   # 人工 long ground truth（只用來標位置）
SPECIAL = {'NVO': [82, 85, 90, 96, 99], 'TMO': [85, 96, 99, 102, 105, 110]}
LO, HI, GAP, SPACING, MAXC = 46, 110, sel.GAP, 2, 5               # 長期範圍與 production 的候選參數（讀 core，不改）
KNOWN_DIAG = {'NVO': [85, 90, 96, 82, 99], 'TMO': [110, 102, 105, 99, 96]}   # 使用者提供的「目前已知」候選（只作比對，不影響計算）

def components(M, ref):
    """重算 score.score_table 內部的 transformed feature 與 percentile（同一份 score.py 函式，不改定義）"""
    F = score.make_features(M); Rr = {c: np.sort(ref[c].to_numpy(float)) for c in score.FEATS}
    pr = {c: score.pct_vs(Rr[c], F[c].to_numpy(float)) for c in score.FEATS}
    return F.set_index('period'), {c: pd.Series(v, index=F['period'].to_numpy()) for c, v in pr.items()}

def replay(pm, sm):
    """逐步重播 core/select.py 的候選產生（長期範圍）。回傳 (cands 週期清單, 每個 index 的 reason, 是否被拜訪, 拜訪時間距是否通過, slot)"""
    best = sm.max(); order = np.argsort(-sm); cands, reason, ok_at_visit, slot, visited = [], {}, {}, {}, set()
    for i in order:
        if sm[i] < best - GAP: break
        visited.add(i); ok = all(abs(pm[i] - c) > SPACING for c in cands); ok_at_visit[i] = ok
        if ok: cands.append(int(pm[i])); reason[i] = 'SELECTED'; slot[i] = len(cands)
        else: reason[i] = 'SPACING_BLOCKED'
        if len(cands) == MAXC: break
    for i in range(len(pm)):
        if i not in reason: reason[i] = 'BELOW_GAP15' if sm[i] < best - GAP else 'TOP5_CAP_REACHED'
    return cands, reason, ok_at_visit, slot, order

def curve(tk, M, S, ref, df, finals):
    P_, Ss = sel.smoothed_scores(S); sm_all = dict(zip(P_, Ss)); raw = S.set_index('period')['分數']; Fm, pr = components(M, ref)
    per = np.arange(LO, HI + 1); pm = per.astype(float); sm = np.array([sm_all[p] for p in per]); best = sm.max()
    cands, reason, ok_at_visit, slot, order = replay(pm, sm); rank = {int(per[i]): k + 1 for k, i in enumerate(order)}
    S_i = S.set_index('period'); rows = []
    for k, p in enumerate(per):
        raw_prev = float(raw[max(p - 1, 15)]); raw_next = float(raw[min(p + 1, 110)])
        rows.append(dict(ticker=tk, period=int(p), tg4_3y=M.set_index('period').loc[p, 'tg4_3y'], qday_3y=M.set_index('period').loc[p, 'qday_3y'], quickfail_3y=M.set_index('period').loc[p, 'quickfail_3y'],
                         f_tg_3y=Fm.loc[p, 'tg_3y'], f_qd_3y=Fm.loc[p, 'qd_3y'], f_quickfail_3y=Fm.loc[p, '快敗_3y'],
                         p_tg_3y=pr['tg_3y'][p], p_qd_3y=pr['qd_3y'][p], **{'p穿插_3y': (pr['tg_3y'][p] + pr['qd_3y'][p]) / 2, 'p快敗_3y': pr['快敗_3y'][p]},
                         **{'分數_長_raw': S_i.loc[p, '分數_長'], 'raw_prev(p-1)': raw_prev, 'raw_self(p)': float(raw[p]), 'raw_next(p+1)': raw_next},
                         smoothed_long_score=sm[k], best_smoothed_score=best, score_gap_from_best=best - sm[k], gap15_cutoff=best - GAP, margin_to_gap15_cutoff=sm[k] - (best - GAP),
                         score_rank=rank[int(p)], within_gap15=bool(sm[k] >= best - GAP), spacing_ok_at_visit=(ok_at_visit[k] if k in ok_at_visit else ''), candidate_selected=reason[k] == 'SELECTED',
                         candidate_slot=slot.get(k, ''), exclusion_reason=reason[k], min_dist_to_selected_cands=min(abs(int(p) - c) for c in cands) if cands else '',
                         is_manual_target=bool(p == TARGETS.get(tk)), is_production_final=bool(p == finals['prod']), is_legacy_final=bool(p == finals['legacy'])))
    C = pd.DataFrame(rows); assert np.allclose(C['p穿插_3y'], S_i.loc[per, 'p穿插_3y']) and np.allclose(C['p快敗_3y'], S_i.loc[per, 'p快敗_3y']), 'component 重算與 score_table 不一致'
    assert np.allclose(C['分數_長_raw'], 0.5 * C['p穿插_3y'] + 0.5 * C['p快敗_3y']), '分數_長 ≠ 0.5·p穿插＋0.5·p快敗（WS 長）'
    return C, cands

def plots(tk, C, cands, out):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    tg = TARGETS[tk]; best = C.best_smoothed_score.iloc[0]
    fig, ax = plt.subplots(figsize=(11, 4.6)); ax.plot(C.period, C.smoothed_long_score, color='tab:blue', lw=1.8, label='smoothed long score (production)'); ax.plot(C.period, C['分數_長_raw'], color='gray', lw=.8, ls=':', label='raw long score (unsmoothed)')
    ax.axhline(best - GAP, color='tab:red', ls='--', lw=1, label=f'best − {GAP} cutoff = {best - GAP:.2f}')
    cc = C[C.period.isin(cands)]; ax.scatter(cc.period, cc.smoothed_long_score, s=70, facecolor='none', edgecolor='k', lw=1.4, zorder=5, label='production candidates')
    for r in cc.itertuples(): ax.annotate(str(r.period), (r.period, r.smoothed_long_score), textcoords='offset points', xytext=(0, 7), ha='center', fontsize=8)
    ax.axvline(tg, color='tab:green', ls='-.', lw=1.2, label=f'manual target SMA{tg}'); ax.set_xlabel('SMA period'); ax.set_ylabel('long score'); ax.set_title(f'{tk}  long score curve (SMA{LO}-{HI}; asof 2026-09-24)', fontsize=10); ax.legend(fontsize=8, loc='best'); ax.set_xlim(LO - 1, HI + 1); fig.tight_layout(); fig.savefig(out / f'{tk}_long_score.png', dpi=100); plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4.6)); ax.plot(C.period, C['p穿插_3y'], color='tab:purple', lw=1.6, label='p穿插_3y  (= (p_tg_3y + p_qd_3y)/2)'.replace('穿插', 'crossing')); ax.plot(C.period, C['p快敗_3y'], color='tab:orange', lw=1.6, label='p快敗_3y'.replace('快敗', 'quickfail'))
    ax.scatter(cc.period, [1] * len(cc), marker='|', s=200, color='k', label='production candidate periods'); ax.axvline(tg, color='tab:green', ls='-.', lw=1.2, label=f'manual target SMA{tg}')
    ax.set_xlabel('SMA period'); ax.set_ylabel('percentile vs reference (0-100)'); ax.set_ylim(0, 102); ax.set_title(f'{tk}  long score components (3y windows)', fontsize=10); ax.legend(fontsize=8, loc='best'); ax.set_xlim(LO - 1, HI + 1); fig.tight_layout(); fig.savefig(out / f'{tk}_long_components.png', dpi=100); plt.close(fig)

def fnum(x): return f'{x:.2f}'
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='diagnostics/long_selector'); ap.add_argument('--work'); ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='lswork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True)
    if fails and not a.synthetic: (out / 'NVO_TMO_long_diagnosis.md').write_text('# DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails) + '\n', encoding='utf-8'); sys.exit(2)
    os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: newM = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in newM.items()], ignore_index=True); dfs = {tk: data.normalize(pd.read_csv(f'data_v/{tk}.csv'), a.asof) for tk in tks}
    # ── 83 檔橫斷面（描述用）＋ NVO／TMO 完整曲線 ──
    curves, allrows, replay_bad, info = {}, [], [], {}
    for tk in tks:
        S = score.score_table(newM[tk], ref); prod = sel.select(dfs[tk], S)['長期']; leg = sel.select(dfs[tk], S, **sel.LEGACY)['長期']; finals = dict(prod=prod['final'], legacy=leg['final'])
        C, cands = curve(tk, newM[tk], S, ref, dfs[tk], finals); allrows.append(C[['ticker', 'period', 'p穿插_3y', 'p快敗_3y', '分數_長_raw', 'smoothed_long_score']])
        if cands != [c['均線'] for c in prod['cands']] or leg['final'] != min(c['均線'] for c in leg['cands'] if c['回測平均'] >= max(x['回測平均'] for x in leg['cands']) - 0.05) or [c['均線'] for c in leg['cands']] != cands: replay_bad.append(tk)
        if tk in TARGETS: curves[tk] = C; info[tk] = dict(cands=cands, prod_final=prod['final'], legacy_final=leg['final'], cand_scores={c['均線']: c['分數'] for c in prod['cands']}, cand_sar={c['均線']: c for c in prod['cands']})
    A = pd.concat(allrows, ignore_index=True)
    for tk in curves: curves[tk].to_csv(out / f'{tk}_long_curve.csv', index=False)
    st = 'DIAGNOSTIC_REPLAY_MISMATCH' if replay_bad else 'OK'
    if replay_bad:
        (out / 'NVO_TMO_long_diagnosis.md').write_text('# STOP — DIAGNOSTIC_REPLAY_MISMATCH\n\n診斷重播的候選／final 與 core/select.py 不一致：' + ', '.join(replay_bad) + '\n', encoding='utf-8'); print(st, replay_bad); sys.exit(3)
    for tk in curves: plots(tk, curves[tk], info[tk]['cands'], out)
    # 與既有 regression／production 輸出比對（資料重抓可能有微幅 drift）
    comp = {}
    try:
        sr = pd.read_csv(ROOT / 'regression/select_results.csv', dtype=str, keep_default_na=False); pf = pd.read_csv(ROOT / 'experiments/production_sanity/production_finals.csv').set_index('ticker')
        for tk in curves:
            r = sr[(sr.ticker == tk) & (sr.range == '長期')].iloc[0]; fc = [int(x.split('(')[0]) for x in r.new_candidates.split()]
            comp[tk] = dict(reg_cands=fc, reg_legacy_final=int(r.new_final), prod_final_file=int(pf.loc[tk, '長期_final']), same_cands=fc == info[tk]['cands'], same_legacy=int(r.new_final) == info[tk]['legacy_final'], same_prod=int(pf.loc[tk, '長期_final']) == info[tk]['prod_final'])
    except Exception as e: comp['error'] = f'{type(e).__name__}: {e}'
    # 83 檔橫斷面（描述用）
    g = A.groupby('period').agg(mean_raw_long=('分數_長_raw', 'mean'), median_raw_long=('分數_長_raw', 'median'), mean_p穿插_3y=('p穿插_3y', 'mean'), mean_p快敗_3y=('p快敗_3y', 'mean'), mean_smoothed_long=('smoothed_long_score', 'mean')).reset_index()
    g.to_csv(out / 'all83_long_by_period.csv', index=False)
    bins = [(46, 60), (61, 75), (76, 90), (91, 110)]
    bt = [dict(bucket=f'{lo}-{hi}', mean_raw_long=A[(A.period >= lo) & (A.period <= hi)]['分數_長_raw'].mean(), mean_p穿插=A[(A.period >= lo) & (A.period <= hi)]['p穿插_3y'].mean(), mean_p快敗=A[(A.period >= lo) & (A.period <= hi)]['p快敗_3y'].mean(),
               n_best=int(sum(1 for tk, d in A.groupby('ticker') if lo <= int(d.loc[d.smoothed_long_score.idxmax(), 'period']) <= hi))) for lo, hi in bins]
    pd.DataFrame(bt).to_csv(out / 'all83_long_bucket_summary.csv', index=False)
    # ── 報告（事實；解讀在報告最上方「答案」區塊）──
    L = []; P = lambda *x: L.append(' '.join(str(i) for i in x))
    P('# NVO／TMO 長期 selector 診斷（純診斷；PRODUCTION CHANGED = NO）\n')
    P(f'- asof {a.asof}｜{len(tks)} 檔資料｜基準＝這 {len(tks)} 檔自己的特徵分佈（同 production_sanity）｜現行 main 的 core｜{"**SYNTHETIC（流程測試，數字無意義）**" if a.synthetic else "真實資料"}')
    P(f'- 候選產生（讀 core/select.py 現行值）：SMA{LO}–{HI}、與 best 差 ≤ {GAP}、與已選距離 > {SPACING}、最多 {MAXC} 條。診斷重播與 `core.select.select()` 的長期候選（含順序）及 final：{len(tks) - len(replay_bad)}/{len(tks)} 檔相同')
    P(f'- smoothed score 是 `core.select.smoothed_scores`（對 S[分數] 做 3 點平均、頭尾 edge-pad）。注意 SMA46 的左鄰居是 SMA45 的「中期分數」（S[分數] 在 ≤33 用短期、34–45 用中期、≥46 用長期）。')
    P('- 分數_長 ＝ 0.5·p穿插_3y ＋ 0.5·p快敗_3y（`score.WS["長"]`）；p穿插_3y ＝ (p_tg_3y ＋ p_qd_3y)／2。已驗證重算值與 score_table 相同。\n')
    for tk in curves:
        C = curves[tk]; i = info[tk]; tgp = TARGETS[tk]; t = C[C.period == tgp].iloc[0]; best = C.best_smoothed_score.iloc[0]
        P(f'## {tk}\n'); P(f'- 現行長期候選（slot 順序）：{" ".join(map(str, i["cands"]))}；production final（Rule B）＝SMA{i["prod_final"]}；LEGACY（min period）final＝SMA{i["legacy_final"]}')
        if tk in comp and 'reg_cands' in comp[tk]: P(f'- 與既有輸出比對：regression/select_results.csv 候選 {" ".join(map(str, comp[tk]["reg_cands"]))}（{"相同" if comp[tk]["same_cands"] else "**不同（data drift）**"}）、LEGACY final {comp[tk]["reg_legacy_final"]}（{"相同" if comp[tk]["same_legacy"] else "**不同**"}）；production_finals.csv 長期 final {comp[tk]["prod_final_file"]}（{"相同" if comp[tk]["same_prod"] else "**不同**"}）')
        P(f'\n**人工 target SMA{tgp}（只用來標位置）**：raw 分數_長 {fnum(t["分數_長_raw"])}；smoothed {fnum(t.smoothed_long_score)}；score_rank {t.score_rank}／65；距 best（{fnum(best)}）{fnum(t.score_gap_from_best)} 分；best−15 cutoff {fnum(best - GAP)}、margin {t.margin_to_gap15_cutoff:+.2f}；within_gap15 ＝ {t.within_gap15}；exclusion_reason ＝ **{t.exclusion_reason}**；spacing_ok_at_visit ＝ {t.spacing_ok_at_visit if t.spacing_ok_at_visit != "" else "（未被拜訪）"}；與最近的已選候選距離 {t.min_dist_to_selected_cands}')
        P(f'- p穿插_3y {fnum(t["p穿插_3y"])}、p快敗_3y {fnum(t["p快敗_3y"])}；原始 tg4_3y {t.tg4_3y}、qday_3y {t.qday_3y}、quickfail_3y {t.quickfail_3y}\n')
        P('### 特別標記的 period\n\n| period | raw 分數_長 | smoothed | rank | 距 best | p穿插_3y | p快敗_3y | exclusion_reason | slot |\n|---|---|---|---|---|---|---|---|---|')
        for p in SPECIAL[tk]:
            r = C[C.period == p].iloc[0]; P(f'| {p} | {fnum(r["分數_長_raw"])} | {fnum(r.smoothed_long_score)} | {r.score_rank} | {fnum(r.score_gap_from_best)} | {fnum(r["p穿插_3y"])} | {fnum(r["p快敗_3y"])} | {r.exclusion_reason} | {r.candidate_slot} |')
        P(f'\n### 依 smoothed score 由高到低的拜訪順序（前 12 名）\n\n| rank | period | smoothed | 距 best | within_gap15 | spacing_ok_at_visit | reason |\n|---|---|---|---|---|---|---|')
        for r in C.sort_values('score_rank').head(12).itertuples(): P(f'| {r.score_rank} | {r.period} | {fnum(r.smoothed_long_score)} | {fnum(r.score_gap_from_best)} | {r.within_gap15} | {r.spacing_ok_at_visit} | {r.exclusion_reason} |')
        within = C[C.within_gap15]; P(f'\n- within_gap15 的 period 共 {len(within)} 條：{within.period.min()}–{within.period.max()}（{", ".join(map(str, within.period))}）')
        pl = C[C.score_gap_from_best <= 1.0]; P(f'- 描述用 plateau 視窗（smoothed 距 best ≤ 1.0 分）：{", ".join(map(str, pl.period))}；視窗內 p穿插_3y {pl["p穿插_3y"].min():.1f}–{pl["p穿插_3y"].max():.1f}（平均 {pl["p穿插_3y"].mean():.1f}）、p快敗_3y {pl["p快敗_3y"].min():.1f}–{pl["p快敗_3y"].max():.1f}（平均 {pl["p快敗_3y"].mean():.1f}）；整條 SMA46–110 平均：p穿插 {C["p穿插_3y"].mean():.1f}、p快敗 {C["p快敗_3y"].mean():.1f}')
        for lo, hi in ((46, 70), (71, 89), (90, 110)):
            s = C[(C.period >= lo) & (C.period <= hi)]; P(f'- SMA{lo}–{hi}：平均 raw {s["分數_長_raw"].mean():.1f}、smoothed {s.smoothed_long_score.mean():.1f}、p穿插 {s["p穿插_3y"].mean():.1f}、p快敗 {s["p快敗_3y"].mean():.1f}')
        P('')
    P('## 共通：長期分數是否隨 period 變長而偏高（描述；83 檔橫斷面）\n\n| SMA 區間 | 平均 raw 分數_長 | 平均 p穿插_3y | 平均 p快敗_3y | 最佳平滑分數落在此區間的檔數 |\n|---|---|---|---|---|')
    for b in bt: P(f'| {b["bucket"]} | {b["mean_raw_long"]:.1f} | {b["mean_p穿插"]:.1f} | {b["mean_p快敗"]:.1f} | {b["n_best"]}/{len(tks)} |')
    P('\n（基準分佈是這 83 檔在 SMA15–110 全部 period 的池化分佈，50 ≈ 池化中位數。完整逐 period 平均見 `all83_long_by_period.csv`。）')
    clean = subprocess.run(['git', 'status', '--porcelain', '--', 'core', 'app.py', 'README.md', 'data', 'regression', 'scripts', 'experiments'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    P(f'\n## 驗證\n\n- NVO／TMO 現行候選可由診斷精確重播：{"是" if st == "OK" else "否"}\n- production／規則／threshold 檔案（core、app.py、README、data、regression、scripts、experiments）在診斷後無變動：{"是" if not clean else "**否：" + clean + "**"}')
    (out / 'NVO_TMO_long_diagnosis.md').write_text('\n'.join(L) + '\n', encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
