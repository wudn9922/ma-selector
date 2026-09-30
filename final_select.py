"""選均線流程（2026-09-29 草案）
1) 加權分數（composite2）：短期15–33、中期34–45、長期46–110 各自排名
2) 候選＝該區間內，分數與最高分相差 ≤15 分的均線（最多5條）（前後各一條平均後的分數；兩兩相差>2）
3) 候選之間用回測比較（簡單＋複雜策略，多空都做；短期看近1年、中期近2年、長期近3年）
4) 最後選擇：候選中回測平均報酬與最好的一條相差 ≤5 個百分點者，取最小的均線（反應快）；否則取回測最好的
"""
import numpy as np, pandas as pd
import ma_select_v18 as ms, bt_engine as bt
D = pd.read_pickle('composite2.pkl').sort_values(['ticker', 'period'])
RANGES = (('短期', 15, 33, 252), ('中期', 34, 45, 504), ('長期', 46, 110, 756))
def smooth(s): return np.convolve(np.r_[s[0], s, s[-1]], np.ones(3) / 3, 'valid')
def run(tk):
    g = D[D.ticker == tk]; P = g.period.to_numpy(); S = smooth(g['分數'].to_numpy())
    df = ms.load(tk); O, H, L, C, V = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close', 'volume')); atr = ms.wilder_atr(df); N = len(C)
    out = {}
    for nm, lo, hi, W in RANGES:
        m = (P >= lo) & (P <= hi); pm, sm = P[m], S[m]
        order = np.argsort(-sm); best = sm[order[0]]; cands = []
        for i in order:
            if sm[i] < best - 15: break
            if all(abs(pm[i] - c['均線']) > 2 for c in cands):
                ma = df.close.rolling(int(pm[i])).mean().to_numpy()
                s1, _ = bt.run(O, H, L, C, V, ma, atr, lo=N - W, mode='simple'); s2, _ = bt.run(O, H, L, C, V, ma, atr, lo=N - W, mode='complex')
                cands.append({'均線': int(pm[i]), '分數': round(float(sm[i]), 1), '簡單報酬': s1['總報酬'], '簡單回撤': s1['最大回撤'], '複雜報酬': s2['總報酬'], '複雜回撤': s2['最大回撤']})
            if len(cands) == 5: break
        for c in cands: c['回測平均'] = (c['簡單報酬'] + c['複雜報酬']) / 2
        bestbt = max(c['回測平均'] for c in cands)
        near = [c for c in cands if c['回測平均'] >= bestbt - 0.05]
        final = min(near, key=lambda c: c['均線'])
        out[nm] = (final['均線'], cands)
    return out
