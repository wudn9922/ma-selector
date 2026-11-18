"""Streamlit cache identities shared by the app and focused regression tests."""
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st
from core import standardize


def data_fingerprint(df):
    """Identify every date/OHLCV row, including CSVs with equal dates and lengths."""
    values = pd.util.hash_pandas_object(df[['date', 'open', 'high', 'low', 'close', 'volume']], index=False)
    return hashlib.sha256(values.to_numpy().tobytes()).hexdigest()


def reference_key(path):
    path = Path(path).resolve()
    return str(path), path.stat().st_mtime_ns


@st.cache_data(show_spinner="基準股票的區間最高分計算中…")
def calc_ref_bests(kind, ref_key, ws_key, _ref, _ws):
    # 路徑區分同 mtime 的台美基準；kind 與權重也各自區分快取。
    return standardize.ref_stock_bests_v2(_ref, _ws) if kind == 'V2' else standardize.ref_stock_bests(_ref, _ws)


def ref_bests(kind, path, ref_df, ws, ws_key):
    # 排名只是參考，讀檔／計算失敗時不影響選線頁面。
    try: return calc_ref_bests(kind, reference_key(path), ws_key, ref_df, ws)
    except Exception: return None
