"""每條均線（15–110）的指標＝metrics_v22（事件）＋ tangle_v4（糾結）＋ extra_metrics（穿插日、快速失敗）"""
import numpy as np, pandas as pd
from . import events as ev, tangle as t4
from .data import wilder_atr
SV = 0.10
PERIODS = range(15, 111)
YEARS = (('1y', 252), ('2y', 504), ('3y', 756))

def period_metrics(O, H, L, C, atr, ma):
    N = len(C); mp = np.r_[np.nan, ma[:-1]]
    brk, wick, rts, _pl, _trs = ev.events(O, H, L, C, ma, atr); r = {}
    for nm, W in (('252', 252), ('504', 504)):
        lo = N - W
        b = [v for v in brk if v['t'] >= lo and v['res'] >= 0]; h = [v for v in b if v['d2']]
        q = [v for v in rts if v['t'] >= lo and v['state'] in ('進場', '失敗') and v['res'] >= 0]
        r[f'A_raw_n@{nm}'] = len(b); r[f'A_raw@{nm}'] = np.mean([v['res'] for v in b]) if b else np.nan
        r[f'A_d2_n@{nm}'] = len(h); r[f'A_d2@{nm}'] = np.mean([v['res'] for v in h]) if h else np.nan
        r[f'A_rt_n@{nm}'] = len(q); r[f'A_rt@{nm}'] = np.mean([v['res'] for v in q]) if q else np.nan
        r[f'A_wick@{nm}'] = sum(1 for v in wick if v['t'] >= lo)
    spans = t4.detect(O, H, L, C, ma, mp, atr); q = t4.qualify(O, H, L, C, ma, mp, atr)
    last = 0; xs = []
    for t in range(N):
        if np.isnan(ma[t]): continue
        d = C[t] - ma[t]; s = 1 if d > SV * atr[t] else (-1 if d < -SV * atr[t] else 0)
        if s:
            if last and s != last: xs.append(t)
            last = s
    for nm, W in YEARS:
        lo = max(N - W, 0)
        r[f'tg4_{nm}'] = sum(1 for _a, e, _h, _l in spans if e >= lo) * 252 / W      # 糾結次數（每年）
        r[f'qday_{nm}'] = q[lo:].sum() * 252 / W                                     # 穿插日（每年）
        xw = [t for t in xs if t >= lo]
        quick = [1 for i, t in enumerate(xs) if t >= lo and i + 1 < len(xs) and xs[i + 1] - t <= 5]
        r[f'quickfail_{nm}'] = len(quick) / len(xw) if xw else 0.                     # 明顯穿越後 5 天內又穿回的比例
    return r

def compute_metrics(df, periods=PERIODS):
    O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df)
    close = df.close; rows = []
    for p in periods:
        r = dict(period=p); r.update(period_metrics(O, H, L, C, atr, close.rolling(p).mean().to_numpy())); rows.append(r)
    return pd.DataFrame(rows)
