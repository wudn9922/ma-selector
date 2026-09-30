"""抓資料（fetch_v 改成回傳 DataFrame）、load、wilder_atr"""
import json, urllib.request
import numpy as np, pandas as pd

def fetch_yahoo(tk, rng="5y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range={rng}&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    res = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
    q, off = res["indicators"]["quote"][0], res["meta"].get("gmtoffset", 0)
    df = pd.DataFrame({"time": [pd.to_datetime(t + off, unit="s").strftime("%Y-%m-%d") for t in res["timestamp"]],
                       "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]})
    return normalize(df)

def normalize(df, asof=None):
    """欄位 time,open,high,low,close,volume → 多一欄 date，排序、去重、去空值；asof 之後的資料截掉"""
    df = df.copy(); df.columns = [str(c).strip().lower() for c in df.columns]
    if "time" not in df.columns and "date" in df.columns: df = df.rename(columns={"date": "time"})
    df["volume"] = df["volume"].fillna(0) if "volume" in df.columns else 0
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["time"])
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    if asof is not None: df = df[df.date <= pd.Timestamp(asof)]
    return df[["time", "open", "high", "low", "close", "volume", "date"]].reset_index(drop=True)

def load(path, asof=None):
    return normalize(pd.read_csv(path), asof)

def wilder_atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().to_numpy()
