import json, time, urllib.request, pandas as pd, sys
from pathlib import Path
for tk in sys.argv[1:]:
    f=Path(f'data_v/{tk}.csv')
    if f.exists(): continue
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range=5y&interval=1d"
    try:
        r=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=30))["chart"]["result"][0]
        q,off=r["indicators"]["quote"][0],r["meta"].get("gmtoffset",0)
        df=pd.DataFrame({"time":[pd.to_datetime(t+off,unit="s").strftime("%Y-%m-%d") for t in r["timestamp"]],
            "open":q["open"],"high":q["high"],"low":q["low"],"close":q["close"],"volume":q["volume"]}).dropna()
        df.to_csv(f,index=False); print(tk,len(df),end='; ')
    except Exception as e: print(tk,'失敗',e)
    time.sleep(0.4)
