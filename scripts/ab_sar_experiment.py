"""純診斷 A/B 實驗：只改「最後選擇用哪種回測」這一個變數（其餘完全相同）。不修改任何 production 預設。
A（Legacy）：gap=15、彼此差>2、最多 5 條、最後選擇用只做多回測（簡單＋複雜平均）＝ core.select.LEGACY
B（SAR-only）：gap=15、彼此差>2、最多 5 條、最後選擇改用 events_v22 多空反手報酬（回測平均＝反手報酬）；其餘與 A 相同
兩者候選由同一段程式決定，理論上必須相同；不同就視為 implementation bug。
輸出：experiments/ab_sar/ab_report.md, ab_hits.csv, ab_per_ticker.csv, ab_candidates.csv, ab_bias_stats.csv, ab_counterfactual.csv
用法：python scripts/ab_sar_experiment.py [--asof 2026-09-24] [--out experiments/ab_sar] [--synthetic] [--only A,B]"""
import argparse, math, os, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R
from core import data, score, select as sel, events as ev
from core.data import wilder_atr
from core.universe import TICKERS

GAP = 15
W_SHORT = 252

def sar_extras(df, period, W):
    """該均線在視窗內的反手交易：筆數、多單／空單筆數、假突破當日出清筆數、持倉天數比例（有持倉的交易日／視窗天數）"""
    O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df); N = len(C); lo = max(N - W, 0)
    ma = df.close.rolling(period).mean().to_numpy(); _b, _w, _r, plog, trades = ev.events(O, H, L, C, ma, atr)
    tr = [t for t in trades if t[1] >= lo]; held = np.zeros(N, bool)
    for a, b, sg, _e, _x, _k in plog:
        if b >= lo: held[max(a, lo):b] = True        # 進場日到出場前一日視為持倉；假突破當日出清不佔天數
    return dict(n=len(tr), n_long=sum(1 for t in tr if t[2] == 1), n_short=sum(1 for t in tr if t[2] == -1), n_wick=sum(1 for t in tr if t[4] == 'F'), exposure=float(held[lo:].mean()))

def dist(f, us): return min(abs(f - u) for u in us)
def spearman(x, y):
    """Spearman＝平均名次的 Pearson（同名次取平均）；有一邊全部相同時回傳 nan"""
    rx, ry = pd.Series(list(x), dtype=float).rank().to_numpy(), pd.Series(list(y), dtype=float).rank().to_numpy()
    if len(rx) < 3 or rx.std() == 0 or ry.std() == 0: return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])
def sign_p(k_short, k_long):
    n = k_short + k_long
    if n == 0: return np.nan
    m = min(k_short, k_long); return min(1., 2 * sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n)
def cluster_ci(D, xc, yc, B=1000, seed=0):
    rng = np.random.default_rng(seed); tks = D.ticker.unique(); g = {t: D[D.ticker == t] for t in tks}; vals = []
    for _ in range(B):
        s = pd.concat([g[t] for t in rng.choice(tks, len(tks))]); vals.append(spearman(s[xc], s[yc]))
    return tuple(np.nanpercentile(vals, [2.5, 97.5]))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='experiments/ab_sar'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='abwork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True); os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: newM = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in newM.items()], ignore_index=True); dfs = {tk: data.normalize(pd.read_csv(f'data_v/{tk}.csv'), a.asof) for tk in tks}
    A_sel, B_sel, cand_rows, per_rows, cf_rows = {}, {}, [], [], []
    for tk in tks:
        Sx = score.score_table(newM[tk], ref)
        A_sel[tk] = sel.select(dfs[tk], Sx, gap=GAP, method='bt', longonly=True)['短期']          # A：Legacy
        B_sel[tk] = sel.select(dfs[tk], Sx, gap=GAP, method='sar', final_rule='min_period')['短期']                      # B：只換最後選擇的回測
    print('選擇完成', flush=True)
    # 候選必須相同
    mism = [tk for tk in tks if [c['均線'] for c in A_sel[tk]['cands']] != [c['均線'] for c in B_sel[tk]['cands']]]
    user = {tk: [p for p in ps if p <= 33] for tk, ps in R.USER.items()}; gt = [tk for tk in tks if user.get(tk)]
    # ── 1) 命中率與距離 ──
    hit = []
    for nm, S_ in (('A_legacy', A_sel), ('B_sar_only', B_sel)):
        for tol in range(4):
            hit.append(dict(experiment=nm, tolerance=tol, candidate_hit=sum(any(abs(u - c['均線']) <= tol for u in user[tk] for c in S_[tk]['cands']) for tk in gt),
                            final_hit=sum(dist(S_[tk]['final'], user[tk]) <= tol for tk in gt), denominator=len(gt)))
    H = pd.DataFrame(hit); H.to_csv(out / 'ab_hits.csv', index=False)
    rows = []
    for tk in gt:
        la, sa = A_sel[tk]['final'], B_sel[tk]['final']; dl, ds = dist(la, user[tk]), dist(sa, user[tk])
        rows.append(dict(ticker=tk, user_MAs=' '.join(map(str, user[tk])), legacy_candidates=' '.join(str(c['均線']) for c in A_sel[tk]['cands']), sar_candidates=' '.join(str(c['均線']) for c in B_sel[tk]['cands']),
                         legacy_final=la, sar_final=sa, legacy_distance=dl, sar_distance=ds, distance_change=ds - dl, classification='IMPROVED' if ds < dl else 'WORSENED' if ds > dl else 'SAME'))
    T = pd.DataFrame(rows); T.to_csv(out / 'ab_per_ticker.csv', index=False)
    # ── 2) 逐候選：結構分數 vs SAR ──
    for tk in tks:
        for i, c in enumerate(B_sel[tk]['cands']):
            x = sar_extras(dfs[tk], c['均線'], W_SHORT); ok = x['n'] == c['反手筆數']
            cand_rows.append(dict(ticker=tk, period=c['均線'], structural_rank=i + 1, structural_score=c['分數'], SAR_total_return=c['反手報酬'], SAR_trade_count=x['n'], SAR_long_count=x['n_long'], SAR_short_count=x['n_short'],
                                  SAR_wick_exit_count=x['n_wick'], SAR_exposure=round(x['exposure'], 3), count_consistent=ok, longonly_simple=c['簡單報酬'], longonly_complex=c['複雜報酬'],
                                  selected_by_SAR_final=c['均線'] == B_sel[tk]['final'], selected_by_legacy_final=c['均線'] == A_sel[tk]['final'], in_61=tk in gt))
    C = pd.DataFrame(cand_rows); C.to_csv(out / 'ab_candidates.csv', index=False)
    stats = []
    def corr_block(D, label):
        for nm, xc, yc in (('period vs SAR_total_return', 'period', 'SAR_total_return'), ('period vs trade_count', 'period', 'SAR_trade_count'), ('trade_count vs SAR_total_return', 'SAR_trade_count', 'SAR_total_return')):
            rho = spearman(D[xc], D[yc]); lo_, hi_ = cluster_ci(D, xc, yc); per = [spearman(g[xc], g[yc]) for _, g in D.groupby('ticker') if len(g) >= 3]; per = [v for v in per if v == v]
            stats.append(dict(scope=label, stat=nm, n_candidates=len(D), pooled_spearman=round(rho, 3), cluster_bootstrap_95ci=f'[{lo_:.3f}, {hi_:.3f}]', within_ticker_mean_spearman=round(float(np.mean(per)), 3) if per else np.nan, n_tickers_within=len(per)))
    corr_block(C, 'all 83 tickers short candidates'); corr_block(C[C.in_61], '61 labelled tickers')
    # ── 3) period shift ──
    def shifts(ids, label):
        rs = []
        for tk in ids:
            g = C[C.ticker == tk]; sbest = int(g[g.structural_rank == 1].period.iloc[0]); sarbest = int(g.loc[g.SAR_total_return.idxmax(), 'period'])
            rs.append(dict(ticker=tk, structural_best=sbest, sar_best=sarbest, legacy_final=A_sel[tk]['final'], sar_final=B_sel[tk]['final']))
        Z = pd.DataFrame(rs)
        for col in ('sar_best', 'sar_final', 'legacy_final'):
            d = Z[col] - Z.structural_best; k_s, k_e, k_l = int((d < 0).sum()), int((d == 0).sum()), int((d > 0).sum())
            stats.append(dict(scope=label, stat=f'{col} − structural_best', n_candidates=len(Z), shorter=k_s, same=k_e, longer=k_l, mean_shift=round(float(d.mean()), 2), median_shift=float(d.median()), sign_test_p=round(sign_p(k_s, k_l), 4)))
        return Z
    Z = shifts([t for t in tks], 'all 83 tickers'); Z61 = shifts(gt, '61 labelled tickers')
    Sx = pd.DataFrame(stats); Sx.to_csv(out / 'ab_bias_stats.csv', index=False)
    # ── 4) counterfactual ──
    cf = Z.copy(); cf['user_MAs'] = cf.ticker.map(lambda t: ' '.join(map(str, user.get(t, [])))); cf['structural_best_score'] = [C[(C.ticker == t) & (C.structural_rank == 1)].structural_score.iloc[0] for t in cf.ticker]
    cf['sar_best_return'] = [C[C.ticker == t].SAR_total_return.max() for t in cf.ticker]; cf['candidates'] = [' '.join(f"{r.period}(s{r.structural_score:.0f},r{r.SAR_total_return*100:+.0f}%,n{r.SAR_trade_count})" for r in C[C.ticker == t].itertuples()) for t in cf.ticker]
    cf.to_csv(out / 'ab_counterfactual.csv', index=False)
    # ── 報告 ──
    L = []; P = lambda *x: L.append(' '.join(str(i) for i in x))
    P(f'# A/B 診斷：只改最後選擇的回測（gap 固定 {GAP}；asof {a.asof}；{len(tks)} 檔，其中 {len(gt)} 檔有短期人工標記）\n')
    P('A＝Legacy（最後選擇用只做多簡單＋複雜平均）；B＝SAR-only（最後選擇用 events_v22 多空反手報酬）。候選規則、平滑、分數完全相同。**未修改任何 production 預設。**\n')
    P(f'候選是否完全相同：{"是（0 檔不同）" if not mism else "**否，" + str(len(mism)) + " 檔不同 → implementation bug：" + str(mism) + "**"}；反手筆數與獨立重算是否一致：{"是" if C.count_consistent.all() else "否"}\n')
    P('## 1. 61 檔短期人工 ground truth\n\n| tolerance | A candidate | B candidate | A final | B final |\n|---|---|---|---|---|')
    for t in range(4):
        h1, h2 = H[(H.experiment == 'A_legacy') & (H.tolerance == t)].iloc[0], H[(H.experiment == 'B_sar_only') & (H.tolerance == t)].iloc[0]
        P(f'| ±{t} | {h1.candidate_hit}/{len(gt)} | {h2.candidate_hit}/{len(gt)} | {h1.final_hit}/{len(gt)} | {h2.final_hit}/{len(gt)} |')
    P(f'\nfinal 到最近人工 MA 的距離：A 平均 {T.legacy_distance.mean():.2f}／中位數 {T.legacy_distance.median():.1f}；B 平均 {T.sar_distance.mean():.2f}／中位數 {T.sar_distance.median():.1f}')
    P(f'\nIMPROVED {int((T.classification == "IMPROVED").sum())}／SAME {int((T.classification == "SAME").sum())}／WORSENED {int((T.classification == "WORSENED").sum())}；final 改變 {int((T.legacy_final != T.sar_final).sum())}/{len(T)} 檔\n')
    P('## 2. 短期偏誤量化（所有短期候選）\n\n' + '\n'.join(['| scope | 統計 | n | 結果 |', '|---|---|---|---|'] + [f"| {r.scope} | {r.stat} | {r.n_candidates} | " + (f"pooled ρ={r.pooled_spearman}，bootstrap 95% CI {r.cluster_bootstrap_95ci}，ticker 內平均 ρ={r.within_ticker_mean_spearman}（{int(r.n_tickers_within)} 檔）" if isinstance(r.cluster_bootstrap_95ci, str) else f"更短 {int(r.shorter)}／相同 {int(r.same)}／更長 {int(r.longer)}，平均 {r.mean_shift}，中位數 {r.median_shift}，符號檢定 p={r.sign_test_p}") + ' |' for r in Sx.itertuples()]))
    P('\n（ticker 內 ρ＝在同一檔股票的候選之間算 Spearman 再對股票平均，避免不同股票的基準差異；pooled 的 CI 是以股票為單位的 bootstrap。）\n')
    P('## 3. Counterfactual（結構分第一 vs SAR 最賺 vs production final）\n\n| 股票 | 人工 | 結構分第一 | SAR 最賺 | A final | B final | 候選（s＝結構分，r＝反手報酬，n＝筆數） |\n|---|---|---|---|---|---|---|')
    for tk in ['SMCI', 'LMT', 'DIS', 'GS', 'TSLA', 'ACN', 'ROST']:
        if tk in set(cf.ticker): r = cf[cf.ticker == tk].iloc[0]; P(f'| {tk} | {r.user_MAs} | {r.structural_best} | {r.sar_best} | {r.legacy_final} | {r.sar_final} | {r.candidates} |')
    # 判定規則（明示）
    def get(scope, stat): return Sx[(Sx.scope == scope) & (Sx.stat == stat)].iloc[0]
    r1 = get('all 83 tickers short candidates', 'period vs SAR_total_return'); lo_, hi_ = [float(v) for v in r1.cluster_bootstrap_95ci.strip('[]').split(',')]; sh = get('all 83 tickers', 'sar_best − structural_best')
    neg = hi_ < 0 and r1.within_ticker_mean_spearman < 0; shorter = sh.shorter > sh.longer and sh.sign_test_p < .05
    verdict = 'YES' if neg and shorter else 'INCONCLUSIVE' if (neg or shorter or (sh.shorter > sh.longer)) else 'NO'
    P(f'\n## 4. 判定（規則事先寫明，僅供參考）\n\nSHORT-MA BIAS DETECTED ＝ **{verdict}**。規則：YES＝(period 與 SAR 報酬的 pooled ρ 之 95% CI 全為負 且 ticker 內平均 ρ<0) 且 (SAR 最賺者比結構分第一更短的檔數 > 更長且符號檢定 p<0.05)；否則若其中任一方向成立或更短>更長為 INCONCLUSIVE；都不成立為 NO。')
    if fails: P('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'ab_report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
