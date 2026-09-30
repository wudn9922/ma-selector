"""metrics_v22（每條均線的事件指標＋糾結次數）— Drive 上沒有這個檔，依交接文件第 7-2 節重建。
迴圈本體逐字取自 7-2；外層（載入資料、npm 迴圈、tg4）依文字說明補上：
  tg4_1y／2y／3y ＝ tangle_v4.detect 的「結束日落在區間內的段數」，近 2 年、3 年除以年數。
輸出格式：out_v22/<ticker>.pkl（ticker,period,A_*）、tg4.pkl（ticker,period,tg4_*），供 composite4.build() 讀取。"""
import numpy as np, pandas as pd
import ma_select_v18 as ms, events_v22 as ev, tangle_v4 as t4

def run_ticker(tk):
    df = ms.load(tk); O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = ms.wilder_atr(df); N = len(C)
    rows, trows = [], []
    for p in range(15, 111):
        ma = df.close.rolling(p).mean().to_numpy(); brk, wick, rts, pl, trs = ev.events(O, H, L, C, ma, atr); r = dict(ticker=tk, period=p)
        for W, nm in ((252, '252'), (504, '504')):
            lo = N - W
            b = [v for v in brk if v['t'] >= lo and v['res'] >= 0]; h = [v for v in b if v['d2']]
            q = [v for v in rts if v['t'] >= lo and v['state'] in ('進場', '失敗') and v['res'] >= 0]
            r[f'A_raw_n@{nm}'] = len(b); r[f'A_raw@{nm}'] = np.mean([v['res'] for v in b]) if b else np.nan
            r[f'A_d2_n@{nm}'] = len(h); r[f'A_d2@{nm}'] = np.mean([v['res'] for v in h]) if h else np.nan
            r[f'A_rt_n@{nm}'] = len(q); r[f'A_rt@{nm}'] = np.mean([v['res'] for v in q]) if q else np.nan
            r[f'A_wick@{nm}'] = sum(1 for v in wick if v['t'] >= lo)
        rows.append(r)
        mp = np.r_[np.nan, ma[:-1]]; spans = t4.detect(O, H, L, C, ma, mp, atr)
        trows.append(dict(ticker=tk, period=p, **{f'tg4_{nm}': sum(1 for a, e, hh, ll in spans if e >= N - W) / yrs for nm, W, yrs in (('1y', 252, 1), ('2y', 504, 2), ('3y', 756, 3))}))
    return pd.DataFrame(rows), pd.DataFrame(trows)
