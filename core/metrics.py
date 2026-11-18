"""每條均線（15–110）的指標＝metrics_v22（事件）＋ tangle_v4（糾結）＋ extra_metrics（穿插日、快速失敗）
tg4_*／qday_* 的「每年」頻率，分母是視窗內糾結判斷真正能算的 K 棒數（t>=1 且前一日均線、ATR 都有值，與 tangle.qualify 的略過條件一致），
不是名目視窗 W；上市較短或均線暖機期（前 period 根）不足 W 根時，才不會被低估而顯得太乾淨。視窗完全可評估時 eff==W，算式與數值不變。"""
import numpy as np, pandas as pd
from . import events as ev, tangle as t4
from .data import wilder_atr
from .ma import moving_average
SV = 0.10
PERIODS = range(15, 111)
YEARS = (('1y', 252), ('2y', 504), ('3y', 756))

QF_H = 5                                                                             # 快敗：明顯穿越後 5 根 K 棒內又反向穿回

def clear_crossings(C, ma, atr):
    """明顯穿越（收盤與均線差 >0.1 ATR 的一側換到另一側）的 K 棒索引"""
    last = 0; xs = []
    for t in range(len(C)):
        if np.isnan(ma[t]): continue
        d = C[t] - ma[t]; s = 1 if d > SV * atr[t] else (-1 if d < -SV * atr[t] else 0)
        if s:
            if last and s != last: xs.append(t)
            last = s
    return xs

def quickfail_counts(xs, lo, N, h=QF_H):
    """視窗（t>=lo）內的快敗統計 → (n, quick, pending)。
    成熟穿越＝t+h<=N-1（後面已有 h 根 K 棒可觀察）；快敗＝下一次穿越與它相隔 <=h 根。
    未成熟（最後 h 根內）的穿越：已經快敗者結果已知，照算（分子分母都計）；尚未快敗者結果未定，不計入分子與分母，另計為 pending（觀察中）。"""
    n = quick = pending = 0
    for i, t in enumerate(xs):
        if t < lo: continue
        failed = i + 1 < len(xs) and xs[i + 1] - t <= h
        if failed: n += 1; quick += 1
        elif t + h <= N - 1: n += 1
        else: pending += 1
    return n, quick, pending

def period_metrics(O, H, L, C, atr, ma):
    N = len(C); mp = np.r_[np.nan, ma[:-1]]
    brk, wick, rts, _pl, _trs = ev.events(O, H, L, C, ma, atr); r = {}
    def win(nm, W):
        lo = N - W
        b = [v for v in brk if v['t'] >= lo and v['res'] >= 0]; h = [v for v in b if v['d2']]
        q = [v for v in rts if v['t'] >= lo and v['state'] in ('進場', '失敗') and v['res'] >= 0]
        r[f'A_raw_n@{nm}'] = len(b); r[f'A_raw@{nm}'] = np.mean([v['res'] for v in b]) if b else np.nan
        r[f'A_d2_n@{nm}'] = len(h); r[f'A_d2@{nm}'] = np.mean([v['res'] for v in h]) if h else np.nan
        r[f'A_rt_n@{nm}'] = len(q); r[f'A_rt@{nm}'] = np.mean([v['res'] for v in q]) if q else np.nan
        r[f'A_wick@{nm}'] = sum(1 for v in wick if v['t'] >= lo)
    for nm, W in (('252', 252), ('504', 504)): win(nm, W)
    spans = t4.detect(O, H, L, C, ma, mp, atr); q = t4.qualify(O, H, L, C, ma, mp, atr)
    xs = clear_crossings(C, ma, atr)
    ok = ~np.isnan(mp) & ~np.isnan(atr); ok[:1] = False                              # 可評估的 K 棒（同 tangle.qualify：t>=1 且 mp、atr 非 NaN）
    for nm, W in YEARS:
        lo = max(N - W, 0)
        eff = max(int(ok[lo:].sum()), 1)                                             # 視窗內實際可評估的棒數（完整視窗時 == W；至少 1，避免除以 0／NaN）
        r[f'tg4_{nm}'] = sum(1 for _a, e, _h, _l in spans if e >= lo) * 252 / eff    # 糾結次數（每年）
        r[f'qday_{nm}'] = q[lo:].sum() * 252 / eff                                   # 穿插日（每年）
        n, quick, _pend = quickfail_counts(xs, lo, N)
        r[f'quickfail_{nm}'] = quick / n if n else 0.                                # 明顯穿越後 5 天內又穿回的比例（只計成熟穿越＋已確定快敗者；無樣本維持 0.，不給 NaN 以免破壞百分位排名）
    win('756', 756)                                                                  # 3 年事件指標（selector v2 用）；放在最後，既有欄位與順序不變
    return r

def compute_metrics(df, periods=PERIODS, kind='SMA'):
    O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df)
    close = df.close; rows = []
    for p in periods:
        r = dict(period=p); r.update(period_metrics(O, H, L, C, atr, moving_average(close, p, kind))); rows.append(r)
    return pd.DataFrame(rows)
