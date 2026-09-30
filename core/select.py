"""選均線流程（final_select）：讀分數表，不讀 pkl
1) 每個區間分數前後各一條平均（平滑）  2) 候選＝與最高分差 ≤ gap（預設 10，網頁可調）、彼此差 ≥3、最多 5 條
3) 候選跑簡單＋複雜回測（短期近1年、中期近2年、長期近3年），取平均  4) 與最好的差 ≤5 個百分點者取最小均線
最後選擇的回測預設用「多空反手」（method='sar'）＝ events_v22 的模擬：一直有持倉，碰到反向邊界就出場並反手，
影線假突破當天收盤出清；扣成本 0.1%。只有這一種策略，「回測平均」＝該報酬。這樣長期下跌的股票也不會因只做多而失真。
候選表另附只做多的簡單／複雜報酬當參考（網頁回測分頁也仍是只做多）。
舊版（研究版 v22）＝ LEGACY（gap=15、method='bt'：回測引擎只做多、簡單＋複雜取平均），regression 用它與 frozen 研究版比對。
"""
import numpy as np, pandas as pd
from . import backtest as bt, events as ev
from .data import wilder_atr
RANGES = (('短期', 15, 33, 252), ('中期', 34, 45, 504), ('長期', 46, 110, 756))
GAP = 10                                   # 候選：與最高分差距上限
LEGACY = dict(gap=15, method='bt', longonly=True)   # 研究版 v22 的設定（只供 regression 使用）

def smooth(s): return np.convolve(np.r_[s[0], s, s[-1]], np.ones(3) / 3, 'valid')

def smoothed_scores(S):
    S = S.sort_values('period'); return S['period'].to_numpy(), smooth(S['分數'].to_numpy())

def sar_stats(O, H, L, C, atr, ma, lo):
    """多空反手（events_v22）：回傳 dict(報酬, 回撤, 勝率, 筆數)。
    報酬＝視窗內（出場日 ≥ lo）各筆淨報酬（已扣成本）複利；回撤＝逐日盤後市值（持倉中按收盤估值）的最大回撤。"""
    N = len(C); _b, _w, _r, plog, trades = ev.events(O, H, L, C, ma, atr)
    ep = {(a, b, sg): e for a, b, sg, e, _x, _k in plog}; tr = sorted([t for t in trades if t[1] >= lo], key=lambda t: (t[0], t[1]))
    eq = np.ones(N); cap = 1.; last = lo
    for tin, tout, sg, r, _k in tr:
        e = ep.get((tin, tout, sg))
        if e is not None:
            for t in range(max(tin, lo), tout): eq[t] = cap * (1 + sg * (C[t] / e - 1))
        cap *= (1 + r); eq[max(tout, lo):] = cap
    seg = np.r_[1., eq[lo:]]; mdd = float((seg / np.maximum.accumulate(seg) - 1).min()); rr = np.array([t[3] for t in tr])
    return dict(報酬=float(cap - 1), 回撤=mdd, 勝率=float((rr > 0).mean()) if len(rr) else np.nan, 筆數=len(rr))

def select(df, S, gap=GAP, method='sar', longonly=True):
    O, H, L, C, V = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close', 'volume')); atr = wilder_atr(df); N = len(C)
    P, Ss = smoothed_scores(S); out = {}
    for nm, lo, hi, W in RANGES:
        m = (P >= lo) & (P <= hi); pm, sm = P[m], Ss[m]
        order = np.argsort(-sm); best = sm[order[0]]; cands = []
        for i in order:
            if sm[i] < best - gap: break
            if all(abs(pm[i] - c['均線']) > 2 for c in cands):
                ma = df.close.rolling(int(pm[i])).mean().to_numpy(); lo_ = max(N - W, 0)
                s1, _ = bt.run(O, H, L, C, V, ma, atr, lo=lo_, mode='simple', longonly=longonly)
                s2, _ = bt.run(O, H, L, C, V, ma, atr, lo=lo_, mode='complex', longonly=longonly)
                c = {'均線': int(pm[i]), '分數': round(float(sm[i]), 1), '簡單報酬': s1['總報酬'], '簡單回撤': s1['最大回撤'], '複雜報酬': s2['總報酬'], '複雜回撤': s2['最大回撤']}
                if method == 'sar':
                    a = sar_stats(O, H, L, C, atr, ma, lo_); c.update({'反手報酬': a['報酬'], '反手回撤': a['回撤'], '反手勝率': a['勝率'], '反手筆數': a['筆數']})
                cands.append(c)
            if len(cands) == 5: break
        for c in cands: c['回測平均'] = c['反手報酬'] if method == 'sar' else (c['簡單報酬'] + c['複雜報酬']) / 2   # 選參數依據
        bestbt = max(c['回測平均'] for c in cands)
        final = min([c for c in cands if c['回測平均'] >= bestbt - 0.05], key=lambda c: c['均線'])
        out[nm] = dict(final=final['均線'], cands=cands, best=round(float(best), 1))
    return out

def suitability(S):
    """股票適合度＝短期最高分（平滑後）；另列長期最高分"""
    P, Ss = smoothed_scores(S)
    return float(Ss[(P >= 15) & (P <= 33)].max()), float(Ss[P >= 46].max())
