"""SUITABILITY_VALIDATION_30 揭盲後的分數拆解（探索性，供使用者對照權重／計算；不屬於凍結的分析計畫，不改任何規則）。
只讀 commit A 封存的 bars.csv 與 scores_table.csv；原始統計用 core/metrics＋core/rawstats 重算（同一份 bars）。
另外附描述用的波動度（近 1 年日報酬年化標準差、ATR/收盤），只為檢查「波動大的股票人工判斷較寬鬆」這個假設，不進任何分數。
用法：python experiments/suitability_validation/score_breakdown.py"""
import json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(ROOT))
RAW = HERE / 'raw_outputs'
W_SHORT = {'突破': .25, '二日': .20, '回測': .15, '雜訊': .15, '穿插': .25}   # core/score.py WS['短']（只引用顯示，不改）

def one(tk):
    from core import data, metrics, rawstats, select as sel, score
    assert score.WS['短'] == W_SHORT
    df = data.normalize(pd.read_csv(RAW / tk / 'bars.csv', float_precision='round_trip')); S = pd.read_csv(RAW / tk / 'scores_table.csv', float_precision='round_trip')
    M = metrics.compute_metrics(df, periods=range(15, 34)).set_index('period'); P, Ss = sel.smoothed_scores(S); sm = dict(zip(P, Ss))
    short = {p: sm[p] for p in range(15, 34)}; best_p = max(short, key=lambda p: (short[p], -p))
    C = df.close.to_numpy(float); atr = data.wilder_atr(df); r = np.diff(np.log(C[-253:]))
    out = dict(vol_1y=float(r.std(ddof=1) * np.sqrt(252)), atr_pct_1y=float(np.mean(atr[-252:] / C[-252:])), best_p=best_p, suit=short[best_p], smooth=short, rows={})
    for p in range(15, 34):
        g = S[S.period == p].iloc[0]; rr = rawstats.raw_row(M.loc[p], rawstats.cross_counts(C, df.close.rolling(p).mean().to_numpy(), atr))
        out['rows'][p] = dict(raw_score=float(g['分數_短']), p突破=float(g['p突破']), p二日=float(g['p二日']), p回測=float(g['p回測']), p雜訊=float(g['p雜訊']), p穿插_1y=float(g['p穿插_1y']), **rr)
    return tk, out

def main():
    an = json.loads((HERE / 'analysis_results.json').read_text(encoding='utf-8')); rows = an['rows']
    with ProcessPoolExecutor(4) as ex: res = dict(ex.map(one, [r['ticker'] for r in rows]))
    T = []
    for r in rows:
        x = res[r['ticker']]; fp = int(r['ma'][3:]); f = x['rows'][fp]; b = x['rows'][x['best_p']]
        assert abs(x['suit'] - r['score']) < 1e-9, r['ticker']
        T.append(dict(order=r['order'], ticker=r['ticker'], rating=r['rating'], stratum=r['stratum'], suitability=round(x['suit'], 1), suit_ma=f"SMA{x['best_p']}",
                      final_ma=r['ma'], final_smoothed=round(x['smooth'][fp], 1), final_raw=round(f['raw_score'], 1),
                      **{f'final_{k}': round(f[k], 0) for k in ('p突破', 'p二日', 'p回測', 'p雜訊', 'p穿插_1y')},
                      **{f'final_{k}': f[k] for k in ('突破成功率', '二日成功率', '回測成功率', '假突破比例', '糾結次數/年(1y/2y/3y)', '穿插日/年(1y/2y/3y)', '快敗率(1y/2y/3y)')},
                      **{f'suitMA_{k}': round(b[k], 0) for k in ('p突破', 'p二日', 'p回測', 'p雜訊', 'p穿插_1y')},
                      vol_1y_pct=round(100 * x['vol_1y'], 1), atr_pct_1y=round(100 * x['atr_pct_1y'], 2)))
    D = pd.DataFrame(T); D.to_csv(HERE / 'score_breakdown.csv', index=False, encoding='utf-8-sig')
    L = ['# SUITABILITY_VALIDATION_30 — 分數拆解（揭盲後、探索性；不改任何規則）\n',
         '- 短期分數＝0.25·突破＋0.20·二日＋0.15·回測＋0.15·雜訊＋0.25·糾結/穿插(1y)，各項是相對 83 檔基準的百分位；適合度＝SMA15–33 平滑分數的最高值。',
         '- 「適合度那條」可能不是你看的那條（最後選擇由反手報酬＋規則 B 決定）。下表同時列兩條。',
         '- 波動度（年化 σ、ATR%）只供對照，沒有進任何分數。\n',
         '| # | 股票 | 你的評分 | 適合度（哪條） | 你看的線 平滑分 | 突破 | 二日 | 回測 | 雜訊 | 糾結/穿插 | 突破成功率 | 假突破比例 | 糾結/年 1y | 年化σ | ATR% |',
         '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for t in T:
        L.append(f"| {t['order']} | {t['ticker']} {t['final_ma']} | {t['rating']} | {t['suitability']}（{t['suit_ma']}） | {t['final_smoothed']} | {t['final_p突破']:.0f} | {t['final_p二日']:.0f} | {t['final_p回測']:.0f} | {t['final_p雜訊']:.0f} | {t['final_p穿插_1y']:.0f} | {t['final_突破成功率']} | {t['final_假突破比例']} | {t['final_糾結次數/年(1y/2y/3y)'].split(' / ')[0]} | {t['vol_1y_pct']}% | {t['atr_pct_1y']}% |")
    g = D.groupby('rating')[['vol_1y_pct', 'atr_pct_1y', 'suitability', 'final_smoothed']].median().reindex(['可用', '勉強', '不可用'])
    L += ['\n## 依你的評分分組的中位數（描述）\n', g.round(1).to_markdown()]
    (HERE / 'score_breakdown.md').write_text('\n'.join(L) + '\n', encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
