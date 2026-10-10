"""均線種類：SMA（簡單）／EMA（指數）。其餘管線只換掉均線序列，規則、門檻、分數公式完全不變
EMA 慣例：alpha = 2/(p+1)，遞迴式 e[t] = a*c[t] + (1-a)*e[t-1]，以第一根收盤當種子（adjust=False）；前 p-1 根遮成 NaN，暖機期與 SMA 一致"""
import numpy as np, pandas as pd
KINDS = ('SMA', 'EMA')

def moving_average(close, p, kind='SMA'):
    """close：pd.Series；回傳 float ndarray（前 p-1 根為 NaN）"""
    if kind == 'SMA': return close.rolling(p).mean().to_numpy()
    if kind == 'EMA': return close.ewm(span=p, adjust=False, min_periods=p).mean().to_numpy()
    raise ValueError(f'kind 必須是 {KINDS}，得到 {kind!r}')
