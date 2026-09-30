"""只讀診斷：為什麼舊實作（frozen research/）在今天的資料上重現不了交接文件的 46/61、17/61、9/12
不修改任何演算法／規則／baseline；只用 research/ 原檔算出舊分數表，輸出證據到 diagnostics/。
用法：python scripts/diagnose_baseline.py [--asof 2026-09-24] [--out diagnostics] [--synthetic] [--only A,B,...]
A. 短期命中率考古（tolerance 0–5、逐檔距離、±1→±2 新增檔、候選／最後選擇的脆弱度）
B. 兩兩比較考古（12 組：原始分、平滑分、margin、各 component、翻轉所需的百分位變化）
C. 資料指紋（每檔筆數、最後日期、收盤價雜湊；供之後比較資料漂移）"""
import argparse, hashlib, os, runpy, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R
from core.universe import TICKERS

PC = ['p突破', 'p二日', 'p回測', 'p雜訊', 'p穿插_1y', 'p穿插_2y', 'p穿插_3y', 'p快敗_1y', 'p快敗_2y', 'p快敗_3y']
RAWC = ['A_raw_n@252', 'A_raw@252', 'A_d2_n@252', 'A_d2@252', 'A_rt_n@252', 'A_rt@252', 'A_wick@252', 'tg4_1y', 'qday_1y', 'quickfail_1y', 'tg4_2y', 'qday_2y', 'quickfail_2y', 'tg4_3y', 'qday_3y', 'quickfail_3y']

def region(p): return '短' if p <= 33 else ('中' if p <= 45 else '長')
def weights(comp, ws):
    """comp＝'短'/'中'/'長'，回傳 {component: (weight, 用哪個 p 欄位)}"""
    med = {k: (ws['短'].get(k, 0) + ws['長'].get(k, 0)) / 2 for k in set(ws['短']) | set(ws['長'])}
    w, y = {'短': (ws['短'], '1y'), '中': (med, '2y'), '長': (ws['長'], '3y')}[comp]
    return {k: (v, f'p穿插_{y}' if k == '穿插' else (f'p快敗_{y}' if k == '快敗' else 'p' + k)) for k, v in w.items()}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='diagnostics'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='diagwork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]; fails = []
    with ProcessPoolExecutor(4) as ex:
        for tk, err in ex.map(R.fetch_one, [(tk, str(wd), a.asof, a.synthetic) for tk in TK]):
            if err: fails.append((tk, err))
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True); os.chdir(wd)
    import ma_select_v18 as ms
    # ── C. 資料指紋 ──
    fp = []
    for tk in tks:
        d = ms.load(tk); fp.append(dict(ticker=tk, rows=len(d), first_date=str(d.date.iloc[0].date()), last_date=str(d.date.iloc[-1].date()), last_close=d.close.iloc[-1],
                                         close_sha=hashlib.sha256(d.close.round(6).to_numpy().tobytes()).hexdigest()[:16], ohlcv_sha=hashlib.sha256(d[['open', 'high', 'low', 'close', 'volume']].round(6).to_numpy().tobytes()).hexdigest()[:16]))
    pd.DataFrame(fp).to_csv(out / 'data_fingerprint.csv', index=False)
    # ── 舊（frozen）流程，同 regression.py ──
    (wd / 'out_v22').mkdir(exist_ok=True)
    with ProcessPoolExecutor(4) as ex: res = list(ex.map(R.old_ticker, tks))
    for tk, (M, T) in zip(tks, res): M.to_pickle(f'out_v22/{tk}.pkl')
    pd.concat([T for _, T in res]).to_pickle('tg4.pkl')
    runpy.run_path(str(ROOT / 'research' / 'extra_metrics.py'), run_name='__main__')
    import composite4; D = composite4.build().sort_values(['ticker', 'period']).reset_index(drop=True); D.to_pickle('composite2.pkl')
    import final_select as fs
    old_sel = {tk: fs.run(tk) for tk in tks}; print('舊流程完成', flush=True)
    D[['ticker', 'period'] + PC + ['分數_短', '分數_中', '分數_長', '分數'] + [c for c in RAWC if c in D.columns]].to_csv(out / 'old_composite.csv.gz', index=False)
    L = []; P = lambda *x: L.append(' '.join(str(i) for i in x))
    P(f'# Baseline 診斷（asof={a.asof}，{len(tks)} 檔；只讀，未修改任何演算法／baseline）\n')
    # ── A. 短期命中率考古 ──
    rows = []; cand_rows = []
    for tk, up in R.USER.items():
        if tk not in old_sel: continue
        us = [p for p in up if p <= 33]
        if not us: continue
        f, cands = old_sel[tk]['短期']; cm = [c['均線'] for c in cands]; best = max(c['分數'] for c in cands); bestbt = max(c['回測平均'] for c in cands)
        for i, c in enumerate(cands):
            cand_rows.append(dict(ticker=tk, rank=i + 1, period=c['均線'], score=c['分數'], score_gap_to_best=round(best - c['分數'], 2), buffer_to_15pt_cutoff=round(c['分數'] - (best - 15), 2),
                                  simple_ret=c['簡單報酬'], complex_ret=c['複雜報酬'], bt_avg=c['回測平均'], bt_gap_to_best=bestbt - c['回測平均'], in_5pp_set=c['回測平均'] >= bestbt - 0.05, is_final=c['均線'] == f))
        rows.append(dict(ticker=tk, user_short_MAs=' '.join(map(str, us)), candidate_MAs=' '.join(f"{c['均線']}({c['分數']})" for c in cands), final_MA=f,
                         min_candidate_distance=min(abs(p - c) for p in us for c in cm), final_distance=min(abs(p - f) for p in us), n_candidates=len(cands)))
    H = pd.DataFrame(rows); H.to_csv(out / 'short_hit_archaeology.csv', index=False); C = pd.DataFrame(cand_rows); C.to_csv(out / 'short_candidates_full.csv', index=False)
    P(f'## A. 短期命中率考古（分母 {len(H)}；交接文件 candidate 46、final 17）\n\n| tolerance | candidate hit | final hit |\n|---|---|---|')
    for t in range(6): P(f'| ±{t} | {(H.min_candidate_distance <= t).sum()} | {(H.final_distance <= t).sum()} |')
    c2 = H[H.min_candidate_distance == 2].ticker.tolist(); f2 = H[H.final_distance == 2].ticker.tolist()
    P(f'\n±1→±2 新增的 candidate hit：{c2}\n\n±1→±2 新增的 final hit：{f2}\n\ncandidate 與 final 的 ±2 新增是否同一檔：{sorted(set(c2) & set(f2)) or "沒有重疊（不同股票）"}\n')
    P('### ±2 candidate：新增檔的脆弱度（buffer＝命中的候選高出「最高分−15」門檻多少分；越小越容易因小幅資料差異掉出候選）\n\n| 股票 | 使用者 | 命中候選 | 該候選分數 | 距門檻 buffer | 候選排名／總數 |\n|---|---|---|---|---|---|')
    for tk in c2:
        us = [int(x) for x in H[H.ticker == tk].user_short_MAs.iloc[0].split()]; g = C[C.ticker == tk]; h = g[g.period.apply(lambda p: min(abs(p - u) for u in us) == 2)].iloc[0]
        P(f'| {tk} | {us} | {int(h.period)} | {h.score} | {h.buffer_to_15pt_cutoff} | {int(h["rank"])}/{len(g)} |')
    P('\n### ±2 final：新增檔的脆弱度（flip distance＝離「回測平均 5 個百分點門檻」最近的候選差多少；越小越容易換人）\n\n| 股票 | 最後選擇 | 其 bt_avg 距最好 | 最接近門檻的候選（差多少） |\n|---|---|---|---|')
    for tk in f2:
        g = C[C.ticker == tk]; fin = g[g.is_final].iloc[0]; d = (g.bt_gap_to_best - 0.05).abs(); j = d.idxmin()
        P(f'| {tk} | {int(fin.period)} | {fin.bt_gap_to_best * 100:.2f}pp | {int(g.loc[j, "period"])}（{d[j] * 100:.2f}pp） |')
    P('\n（以上是「哪一檔最容易因微小資料／實作差異而改變」的證據排序，不是對 baseline 定義的認定。）\n')
    # ── B. 兩兩比較考古 ──
    pw = []; comp_rows = []; flip_rows = []
    for tk, p1, p2, ge in R.PAIRS:
        if tk not in old_sel: continue
        g = D[D.ticker == tk].set_index('period'); sm = dict(zip(g.index, fs.smooth(g['分數'].to_numpy())))
        ra, rb = region(p1), region(p2); wa, wb = weights(ra, composite4.WS), weights(rb, composite4.WS)
        margin = g.loc[p1, '分數'] - g.loc[p2, '分數']
        pw.append(dict(ticker=tk, period_a=p1, period_b=p2, relation='>=' if ge else '>', region_a=ra, region_b=rb, score_a=g.loc[p1, '分數'], score_b=g.loc[p2, '分數'], margin_raw=margin,
                       smooth_a=sm[p1], smooth_b=sm[p2], margin_smooth=sm[p1] - sm[p2], user_order_holds_raw=bool(margin > 0 or (ge and margin == 0)), user_order_holds_smooth=bool(sm[p1] - sm[p2] > 0),
                       **{f'a_{c}': g.loc[p1, c] for c in PC}, **{f'b_{c}': g.loc[p2, c] for c in PC}, **{f'a_{c}': g.loc[p1, c] for c in RAWC if c in g.columns}, **{f'b_{c}': g.loc[p2, c] for c in RAWC if c in g.columns}))
        for who, per, w in (('a', p1, wa), ('b', p2, wb)):
            for k, (wt, col) in w.items(): comp_rows.append(dict(ticker=tk, side=who, period=per, component=k, p_column=col, percentile=g.loc[per, col], weight=wt, contribution=wt * g.loc[per, col]))
        for k in set(wa) | set(wb):
            ca = wa[k][0] * g.loc[p1, wa[k][1]] if k in wa else 0.; cb = wb[k][0] * g.loc[p2, wb[k][1]] if k in wb else 0.
            flip_rows.append(dict(ticker=tk, component=k, contribution_a=ca, contribution_b=cb, contribution_diff_a_minus_b=ca - cb,
                                  pct_points_needed_on_A_to_flip=margin / wa[k][0] if k in wa and wa[k][0] else np.nan, pct_points_needed_on_B_to_flip=margin / wb[k][0] if k in wb and wb[k][0] else np.nan))
    PW = pd.DataFrame(pw); PW.to_csv(out / 'pairwise_archaeology.csv', index=False); pd.DataFrame(comp_rows).to_csv(out / 'pairwise_components_long.csv', index=False); FL = pd.DataFrame(flip_rows); FL.to_csv(out / 'pairwise_flip_requirements.csv', index=False)
    P('## B. 兩兩比較考古（交接文件 9/12，錯的是 LMT、ACN、DIS）\n')
    P(f'今天舊實作：未平滑 {int(PW.user_order_holds_raw.sum())}/{len(PW)}，錯的 {PW[~PW.user_order_holds_raw].ticker.tolist()}；平滑 {int(PW.user_order_holds_smooth.sum())}/{len(PW)}，錯的 {PW[~PW.user_order_holds_smooth].ticker.tolist()}\n')
    P('| 股票 | A vs B | 原始分 A/B | margin | 平滑分 A/B | 平滑 margin |\n|---|---|---|---|---|---|')
    for r in pw: P(f"| {r['ticker']} | {r['period_a']}{r['relation']}{r['period_b']}（{r['region_a']}/{r['region_b']}） | {r['score_a']:.2f} / {r['score_b']:.2f} | {r['margin_raw']:+.2f} | {r['smooth_a']:.2f} / {r['smooth_b']:.2f} | {r['margin_smooth']:+.2f} |")
    for tk in ('LMT', 'ACN', 'DIS'):
        if tk not in old_sel: continue
        r = PW[PW.ticker == tk].iloc[0]; P(f"\n### {tk} {r.period_a} vs {r.period_b}：margin {r.margin_raw:+.3f}\n\n| component | A 的 p | B 的 p | 貢獻差(A−B) | 只改 A 需降低 | 只改 B 需升高 |\n|---|---|---|---|---|---|")
        wa = weights(r.region_a, composite4.WS)
        for k in wa:
            f_ = FL[(FL.ticker == tk) & (FL.component == k)].iloc[0]; col = wa[k][1]
            P(f"| {k}（{col}，權重 {wa[k][0]:.3f}） | {r['a_' + col]:.1f} | {r['b_' + col]:.1f} | {f_.contribution_diff_a_minus_b:+.2f} | {f_.pct_points_needed_on_A_to_flip:.1f} 個百分位 | {f_.pct_points_needed_on_B_to_flip:.1f} 個百分位 |")
        P('\n原始欄位（@252 事件數與比率、近 1 年糾結／穿插日）：\n\n| 欄位 | A | B |\n|---|---|---|')
        for c in RAWC:
            if 'a_' + c in r.index and not c.endswith(('2y', '3y')): P(f"| {c} | {r['a_' + c]:.4g} | {r['b_' + c]:.4g} |")
    P('\n## C. 資料指紋\n\n已寫入 `data_fingerprint.csv`（每檔筆數、首末日期、收盤價／OHLCV 雜湊）。目前沒有更早的原始快照可比對，這份指紋只是為了以後能偵測漂移。')
    if fails: P('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'diagnose_report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
