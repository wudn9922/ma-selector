"""回歸檢查：用真實資料（GitHub Actions 抓 Yahoo）重現研究版驗證結果（交接文件第 5 節）
用法：python scripts/regression.py [--asof 2026-09-24] [--out regression]
基準＝這 83 檔在 asof 當天的分佈（同 composite4 的做法），所以應該可以重現研究版的數字。
輸出：regression/report.md、select_results.csv、charts/*.png"""
import argparse, re, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import data, metrics, score, select as sel, charts
from core.universe import TICKERS

USER_TXT = """AAPL[24,58] ABT[35,38] ACN[25,27,32,46] ADBE[20,63] AEP[33] ALSN[19,32,45] AMD[32,104] ASML[24,58] AVGO[29] BAC[17,22,75] BB[17,38] CME[21,35] COST[80] CRWD[29,31,42] CSX[18] CVX[25] DIS[18,25,37] DUK[25,27,38] EOG[23] ETN[28] GE[18,40] GOOGL[23,55,89] GS[18] IBM[24,36] INTC[23] INTU[24] JNJ[26,27] KMB[21,39,87,94] LCII[22,30,54] LLY[33] LMT[16,18,80,93] LULU[18,47] META[25,75] MLR[57] MMS[26,30] MP[35] MSFT[25,59] MU[27,60] NKE[36] NOK[17,41] NU[17,50,78] NVO[22,27,64] ODFL[17,21,44,51] PEP[97,110] PGR[23,34,96] PLTR[30,37] PYPL[29,56] ROST[23] RRX[21] RTX[22,33,45,47] SAIC[37] SBUX[40] SCHW[21,37] SFM[24] SMCI[24] SOFI[35] SSD[18,68] TGT[20,34,40] TMO[25,85] TSCO[25,107] TSLA[20] TSM[27,37,64] TTC[29,85] TXRH[19,25,34] UHS[27,76] UNP[27] UPS[17,23,26,47] WDFC[27,85] WSO[19,59] ZTS[30,56]"""
USER = {m.group(1): [int(x) for x in m.group(2).split(',')] for m in re.finditer(r'([A-Z]+)\[([\d,]+)\]', USER_TXT)}
# 使用者判斷過的兩兩比較（左邊比較好；ge=True 表示 ≥）
PAIRS = [('GS', 39, 18, 0), ('JNJ', 34, 26, 0), ('LMT', 18, 33, 0), ('AVGO', 38, 29, 0), ('LULU', 18, 26, 0), ('SMCI', 24, 37, 0),
         ('TSLA', 20, 29, 0), ('ACN', 32, 25, 0), ('PLTR', 30, 28, 0), ('BAC', 75, 62, 0), ('DIS', 19, 32, 1), ('CRWD', 31, 15, 0)]
BASE = dict(pairs=9, pairs_wrong={'LMT', 'ACN', 'DIS'}, short_cand=46, short_final=17, long_cand=16)   # 研究版 v22
CHARTS = [('LULU', 18), ('SMCI', 24), ('GE', 40)]

def get(tk, asof):
    for k in range(4):
        try: return data.normalize(data.fetch_yahoo(tk), asof)
        except Exception as e: err = e; time.sleep(2 * (k + 1))
    raise RuntimeError(f'{tk}: {err}')

def work(a):
    tk, asof = a; df = get(tk, asof); return tk, df, metrics.compute_metrics(df)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='regression'); a = ap.parse_args()
    out = Path(a.out); (out / 'charts').mkdir(parents=True, exist_ok=True); t0 = time.time(); D, Ms, fails = {}, {}, []
    with ProcessPoolExecutor(4) as ex:
        for f in [ex.submit(work, (tk, a.asof)) for tk in TICKERS]:
            try: tk, df, M = f.result(); D[tk] = df; Ms[tk] = M
            except Exception as e: fails.append(str(e)); print('失敗', e, flush=True)
    print(f'抓資料＋指標 {len(D)}/{len(TICKERS)} 檔，{time.time()-t0:.0f}s', flush=True)
    if len(D) < len(TICKERS) - 3: sys.exit('成功的股票太少，中止')
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in Ms.items()], ignore_index=True)
    S = {tk: score.score_table(M, ref) for tk, M in Ms.items()}; R = {}; rows = []
    for tk in D:
        R[tk] = sel.select(D[tk], S[tk])
        for nm, r in R[tk].items(): rows.append(dict(ticker=tk, range=nm, final=r['final'], best=r['best'], cands=' '.join(f"{c['均線']}({c['分數']})" for c in r['cands'])))
    pd.DataFrame(rows).to_csv(out / 'select_results.csv', index=False)
    L = []; P = lambda *x: L.append(' '.join(str(i) for i in x))
    P(f'# 回歸檢查（asof={a.asof}，{len(D)} 檔，基準＝這 {len(D)} 檔自己）\n')
    # 1) 兩兩比較
    P('## 1. 兩兩比較（左邊應該比較好）\n\n| 股票 | 比較 | 未平滑分數 | 平滑分數 | 結果 |\n|---|---|---|---|---|'); wrong = set(); okc = 0
    for tk, p1, p2, ge in PAIRS:
        if tk not in S: P(f'| {tk} | {p1} vs {p2} | 無資料 | | FAIL |'); wrong.add(tk); continue
        g = S[tk].set_index('period')['分數']; P_, Ss = sel.smoothed_scores(S[tk]); sm = dict(zip(P_, Ss))
        ok = (g[p1] >= g[p2]) if ge else (g[p1] > g[p2]); okc += ok; ok2 = (sm[p1] >= sm[p2]) if ge else (sm[p1] > sm[p2])
        if not ok: wrong.add(tk)
        P(f'| {tk} | {p1}{"≥" if ge else ">"}{p2} | {g[p1]:.1f} vs {g[p2]:.1f} | {sm[p1]:.1f} vs {sm[p2]:.1f}（{"一致" if ok2 else "不一致"}） | {"PASS" if ok else "FAIL"} |')
    P(f'\n未平滑分數一致 **{okc}/12**（研究版 {BASE["pairs"]}/12，錯的是 {sorted(BASE["pairs_wrong"])}）；這次錯的：{sorted(wrong)}\n')
    # 2) 候選命中率
    sc = sf = lc = lf = ns = nl = 0; sc_miss = []; lc_miss = []
    for tk, up in USER.items():
        if tk not in R: continue
        us = [p for p in up if p <= 33]; ul = [p for p in up if p > 45]
        if us:
            ns += 1; cs = [c['均線'] for c in R[tk]['短期']['cands']]; sc += any(p in cs for p in us); sf += R[tk]['短期']['final'] in us
            if not any(p in cs for p in us): sc_miss.append(tk)
        if ul:
            nl += 1; cl = [c['均線'] for c in R[tk]['長期']['cands']]; lc += any(abs(p - c) <= 5 for p in ul for c in cl); lf += any(abs(R[tk]['長期']['final'] - p) <= 5 for p in ul)
            if not any(abs(p - c) <= 5 for p in ul for c in cl): lc_miss.append(tk)
    P('## 2. 候選命中率\n\n| 項目 | 這次 | 研究版 v22 | 判定 |\n|---|---|---|---|')
    for nm, v, b, n in (('短期候選包含使用者的均線', sc, BASE['short_cand'], ns), ('短期最後選擇＝使用者的均線', sf, BASE['short_final'], ns), ('長期候選包含使用者的均線（差 ≤5）', lc, BASE['long_cand'], nl)):
        P(f'| {nm} | {v}/{n} | {b}/{n} | {"PASS（相同）" if v == b else ("PASS（較好）" if v > b else "FAIL（較差）")} |')
    P(f'\n長期最後選擇在使用者均線 ±5 內：{lf}/{nl}（參考用，研究版沒有數字）\n\n短期候選沒對到：{" ".join(sc_miss)}\n\n長期候選沒對到：{" ".join(lc_miss)}\n')
    # 3) 圖
    P('## 3. 判定圖抽查（要人工對照研究版）\n')
    for tk, p in CHARTS:
        if tk not in D: continue
        g = S[tk][S[tk].period == p].iloc[0]
        title = f"{tk} SMA{p}｜分數 短{g['分數_短']:.0f} 中{g['分數_中']:.0f} 長{g['分數_長']:.0f}｜突破{g['p突破']:.0f} 二日{g['p二日']:.0f} 回測{g['p回測']:.0f} 雜訊{g['p雜訊']:.0f} 穿插1y {g['p穿插_1y']:.0f} 快敗3y {g['p快敗_3y']:.0f}"
        (out / 'charts' / f'{tk}_{p}.png').write_bytes(charts.chart_png(D[tk], p, title)); P(f'- `charts/{tk}_{p}.png`：{title}')
    # 4) 選擇結果
    P('\n## 4. 各股選擇結果（節錄前 20 檔，完整見 select_results.csv）\n\n| 股票 | 使用者 | 短期選 | 中期選 | 長期選 |\n|---|---|---|---|---|')
    for tk in list(R)[:20]: P(f'| {tk} | {USER.get(tk, "")} | {R[tk]["短期"]["final"]} | {R[tk]["中期"]["final"]} | {R[tk]["長期"]["final"]} |')
    if fails: P('\n## 抓不到資料\n' + '\n'.join('- ' + f for f in fails))
    (out / 'report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
