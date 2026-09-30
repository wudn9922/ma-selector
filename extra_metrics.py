import numpy as np, pandas as pd
from pathlib import Path
import ma_select_v18 as ms, tangle_v4 as t4
SV=0.10
rows=[]
for f in sorted(Path('data_v').glob('*.csv')):
    tk=f.stem
    if tk=='MRNA': continue
    df=ms.load(tk); O,H,L,C=(df[k].to_numpy(float) for k in ('open','high','low','close')); atr=ms.wilder_atr(df); N=len(C)
    for p in range(15,111):
        ma=df.close.rolling(p).mean().to_numpy(); mp=np.r_[np.nan,ma[:-1]]
        q=t4.qualify(O,H,L,C,ma,mp,atr)
        last=0; xs=[]; sides=[]
        for t in range(N):
            if np.isnan(ma[t]): continue
            d=C[t]-ma[t]; s=1 if d>SV*atr[t] else (-1 if d<-SV*atr[t] else 0)
            if s:
                if last and s!=last: xs.append(t)
                last=s
        r={'ticker':tk,'period':p}
        for W,nm in ((252,'1y'),(504,'2y'),(756,'3y')):
            lo=N-W
            r[f'qday_{nm}']=q[lo:].sum()*252/W                    # 穿插日（每年）
            xw=[t for t in xs if t>=lo]
            r[f'cross_{nm}']=len(xw)*252/W                        # 明顯穿越次數（每年）
            quick=[1 for i,t in enumerate(xs) if t>=lo and i+1<len(xs) and xs[i+1]-t<=5]
            r[f'quickfail_{nm}']=len(quick)/len(xw) if xw else 0.  # 突破後 5 天內又穿回去的比例
        rows.append(r)
pd.DataFrame(rows).to_pickle('extra_metrics.pkl'); print(len(rows))
