"""抓資料（fetch_v 改成回傳 DataFrame）、load、wilder_atr"""
import json, urllib.request
import numpy as np, pandas as pd

def fetch_yahoo(tk, rng="5y", adjust=True):
    """抓 Yahoo 日線。adjust=True（預設）→ 用 adjclose/close 還原股利（價格已含拆股還原，這裡補除息），volume 不動；
    adjclose 缺漏／長度不符／壞值 → 不還原照常回傳。結果記在 df.attrs['adjusted']。adjust=False → 與舊版逐位元組相同（凍結證據腳本用）"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range={rng}&interval=1d" + ("&events=div%2Csplits" if adjust else "")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    res = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
    return parse_chart(res, adjust)

def parse_chart(res, adjust=True):
    """chart result（dict）→ DataFrame；不做網路。分開寫是為了能用合成 payload 測試"""
    q, off = res["indicators"]["quote"][0], res["meta"].get("gmtoffset", 0)
    df = pd.DataFrame({"time": [pd.to_datetime(t + off, unit="s").strftime("%Y-%m-%d") for t in res["timestamp"]],
                       "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]})
    f = div_factor(res, df["close"]) if adjust else None
    if f is not None:
        for c in ("open", "high", "low", "close"): df[c] = pd.to_numeric(df[c], errors="coerce") * f
    df.attrs["adjusted"] = f is not None
    return normalize(df)

def div_factor(res, close):
    """每根 factor = adjclose / close（numpy 陣列）；任何異常回傳 None（＝不還原）。
    close 為空值的那根（normalize 會丟掉）factor 用 1.0；其餘 close／adjclose 必須是有限正數，否則整條序列視為無法還原"""
    try:
        a = res["indicators"]["adjclose"][0]["adjclose"]
        if not isinstance(a, list) or len(a) != len(close) or len(res["timestamp"]) != len(close): return None
        c = pd.to_numeric(pd.Series(list(close), dtype=object), errors="coerce").to_numpy(float)
        a = pd.to_numeric(pd.Series(a, dtype=object), errors="coerce").to_numpy(float)
        f = np.ones(len(c)); ok = ~np.isnan(c)
        if not (np.isfinite(c[ok]).all() and (c[ok] > 0).all() and np.isfinite(a[ok]).all() and (a[ok] > 0).all()): return None
        f[ok] = a[ok] / c[ok]; return f
    except Exception: return None

def normalize(df, asof=None):
    """欄位 time,open,high,low,close,volume → 多一欄 date，排序、去重、去空值；asof 之後的資料截掉"""
    attrs = dict(df.attrs); df = df.copy(); df.columns = [str(c).strip().lower() for c in df.columns]
    if "time" not in df.columns and "date" in df.columns: df = df.rename(columns={"date": "time"})
    df["volume"] = df["volume"].fillna(0) if "volume" in df.columns else 0
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["time"])
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    if asof is not None: df = df[df.date <= pd.Timestamp(asof)]
    df = df[["time", "open", "high", "low", "close", "volume", "date"]].reset_index(drop=True); df.attrs.update(attrs)   # attrs（如 adjusted）要保留
    return df

def load(path, asof=None):
    return normalize(pd.read_csv(path), asof)

def wilder_atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().to_numpy()
