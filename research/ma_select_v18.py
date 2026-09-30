"""shim：交接文件第 7-1 節的 load／wilder_atr（原本在 ma_select_v18.py，Drive 上沒有）。程式碼逐字取自交接文件；
唯一差別：ASOF 由環境變數 ASOF 指定（回歸固定 2026-09-24）。相對路徑 data_v/ 以工作目錄為準。"""
import os
import pandas as pd
ASOF = pd.Timestamp(os.environ.get('ASOF', '2026-09-24'))
def load(tk):
    df = pd.read_csv(f"data_v/{tk}.csv"); df["date"] = pd.to_datetime(df.time)
    return df[df.date <= ASOF].reset_index(drop=True)
def wilder_atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().to_numpy()
