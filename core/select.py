"""選均線流程（final_select）：讀分數表，不讀 pkl
1) 每個區間分數前後各一條平均（平滑）  2) 候選＝與最高分差 ≤15、彼此差 ≥3、最多 5 條
3) 候選跑簡單＋複雜回測（短期近1年、中期近2年、長期近3年），取平均  4) 與最好的差 ≤5 個百分點者取最小均線
"""
import numpy as np, pandas as pd
from . import backtest as bt
from .data import wilder_atr
RANGES = (('短期', 15, 33, 252), ('中期', 34, 45, 504), ('長期', 46, 110, 756))

def smooth(s): return np.convolve(np.r_[s[0], s, s[-1]], np.ones(3) / 3, 'valid')

def smoothed_scores(S):
    S = S.sort_values('period'); return S['period'].to_numpy(), smooth(S['分數'].to_numpy())

def select(df, S):
    O, H, L, C, V = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close', 'volume')); atr = wilder_atr(df); N = len(C)
    P, Ss = smoothed_scores(S); out = {}
    for nm, lo, hi, W in RANGES:
        m = (P >= lo) & (P <= hi); pm, sm = P[m], Ss[m]
        order = np.argsort(-sm); best = sm[order[0]]; cands = []
        for i in order:
            if sm[i] < best - 15: break
            if all(abs(pm[i] - c['均線']) > 2 for c in cands):
                ma = df.close.rolling(int(pm[i])).mean().to_numpy()
                s1, _ = bt.run(O, H, L, C, V, ma, atr, lo=max(N - W, 0), mode='simple'); s2, _ = bt.run(O, H, L, C, V, ma, atr, lo=max(N - W, 0), mode='complex')
                cands.append({'均線': int(pm[i]), '分數': round(float(sm[i]), 1), '簡單報酬': s1['總報酬'], '簡單回撤': s1['最大回撤'],
                              '複雜報酬': s2['總報酬'], '複雜回撤': s2['最大回撤']})
            if len(cands) == 5: break
        for c in cands: c['回測平均'] = (c['簡單報酬'] + c['複雜報酬']) / 2
        bestbt = max(c['回測平均'] for c in cands)
        final = min([c for c in cands if c['回測平均'] >= bestbt - 0.05], key=lambda c: c['均線'])
        out[nm] = dict(final=final['均線'], cands=cands, best=round(float(best), 1))
    return out

def suitability(S):
    """股票適合度＝短期最高分（平滑後）；另列長期最高分"""
    P, Ss = smoothed_scores(S)
    return float(Ss[(P >= 15) & (P <= 33)].max()), float(Ss[P >= 46].max())
