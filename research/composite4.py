"""均線加權分數 v4（事件改用 events_v22：多空反手＋假突破後空手＋新回測規則）
指標來源：metrics_v22（= metrics_v21.py 把 events_v21 換成 events_v22、輸出資料夾 out_v22）
以下沿用 v2：
均線加權分數 v2（0–100，跨股票標準化）— 2026-09-28
短期（15–33）：希望快進快出吃到獲利 → 看近 1 年
  突破成功率 25%｜二日法則 20%｜回測成功率 15%｜雜訊比例 15%｜糾結+穿插 25%
長期（46–110）：希望明確分出多空，最怕「突破沒幾天就跌回」 → 看近 3 年
  突破後 5 天內又穿回的比例（快速失敗）50%｜糾結+穿插 50%
中期（34–45）：兩組權重平均，看近 2 年的「快速失敗」與「穿插」、近 1 年的成功率
「糾結+穿插」＝糾結次數與穿插日數各自百分位的平均（越少越好）
成功率用 Wilson 下界；每項換成在所有股票×均線中的百分位（0–100）
選均線流程 final_select（候選＝與最高分差 ≤15 分、最多5條；回測用 bt_engine v1 只做多；回測平均差 ≤5 個百分點取最小均線）
"""
import numpy as np, pandas as pd, glob
def wlb(p, n, z=1.0):
    p = np.nan_to_num(p); n = np.maximum(np.nan_to_num(n), 1e-9)
    return (p + z*z/(2*n) - z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)
WS = {'短': {'突破': .25, '二日': .20, '回測': .15, '雜訊': .15, '穿插': .25},
      '長': {'快敗': .50, '穿插': .50}}
def build():
    M = pd.concat([pd.read_pickle(f) for f in glob.glob('out_v22/*.pkl')])
    T = pd.read_pickle('tg4.pkl'); X = pd.read_pickle('extra_metrics.pkl')
    D = M.merge(T, on=['ticker', 'period']).merge(X, on=['ticker', 'period'])
    pr = lambda s: pd.Series(np.asarray(s, float), index=D.index).rank(pct=True) * 100
    D['p突破'] = pr(wlb(D['A_raw@252'], D['A_raw_n@252'])); D['p二日'] = pr(wlb(D['A_d2@252'], D['A_d2_n@252']))
    D['p回測'] = pr(wlb(D['A_rt@252'], D['A_rt_n@252']))
    D['p雜訊'] = pr(-(D['A_wick@252'] / (D['A_wick@252'] + D['A_raw_n@252']).clip(lower=1)))
    for nm in ('1y', '2y', '3y'):
        D[f'p穿插_{nm}'] = (pr(-D[f'tg4_{nm}']) + pr(-D[f'qday_{nm}'])) / 2
        D[f'p快敗_{nm}'] = pr(-D[f'quickfail_{nm}'])
    D['分數_短'] = sum(w * (D['p穿插_1y'] if k == '穿插' else D['p' + k]) for k, w in WS['短'].items())
    D['分數_長'] = sum(w * (D['p穿插_3y'] if k == '穿插' else (D['p快敗_3y'] if k == '快敗' else D['p' + k])) for k, w in WS['長'].items())
    med = {k: (WS['短'].get(k, 0) + WS['長'].get(k, 0)) / 2 for k in set(WS['短']) | set(WS['長'])}
    D['分數_中'] = sum(w * (D['p穿插_2y'] if k == '穿插' else (D['p快敗_2y'] if k == '快敗' else D['p' + k])) for k, w in med.items())
    D['分數'] = np.where(D.period <= 33, D['分數_短'], np.where(D.period <= 45, D['分數_中'], D['分數_長']))
    return D
