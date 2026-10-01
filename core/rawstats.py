"""原始機率／比率／頻率的顯示輔助（只讀 core/metrics.py 已算好的欄位；不重新定義任何指標、不影響 selector／score）。
percentile（p突破…）是「相對 reference pool 的百分位分數」，不是發生機率；這裡呈現的是實際統計：
  成功率（突破 A_raw、二日 A_d2、回測 A_rt）＝成功次數／已判定次數（附 n）；假突破比例＝A_wick／(A_wick＋A_raw_n)（正向呈現，不用 score.py 取負號後的 feature）
  糾結次數/年 tg4_*、穿插日/年 qday_* ＝ 年化「頻率」（不是機率）；快敗率 quickfail_* ＝ 比率（附明顯穿越次數）
分母為 0 或 NaN 一律顯示「— (n=0)」，不顯示 0%。
"""
import numpy as np
SV = 0.10
YEARS = (('1y', 252), ('2y', 504), ('3y', 756))

def _ok(x): return x is not None and not (isinstance(x, float) and np.isnan(x))

def fmt_rate(rate, n, digits=1):
    """成功率／比率：'62.5% (n=8)'；n 為 0／NaN → '— (n=0)'"""
    n = int(n) if _ok(n) else 0
    if n <= 0 or not _ok(rate): return '— (n=0)'
    return f'{rate * 100:.{digits}f}% (n={n})'

def fmt_freq(x, digits=2):
    """年化頻率（次/年）：'1.50'；NaN → '—'"""
    return '—' if not _ok(x) else f'{x:.{digits}f}'

def fmt_triplet(vals, fmt):
    return ' / '.join(fmt(v) for v in vals)

def wick_ratio(wick, breakouts):
    """假突破比例＝wick／(wick＋已判定突破)；分母 0 → (nan, 0)"""
    d = (wick if _ok(wick) else 0) + (breakouts if _ok(breakouts) else 0)
    return (np.nan, 0) if d <= 0 else (wick / d, int(d))

def cross_counts(C, ma, atr, N=None):
    """快敗率的分母：各年視窗內「明顯穿越」次數 xw 與其中 5 天內又穿回的次數（與 core/metrics.py 的 quickfail 相同的計算；只為了得到 n）。回傳 {'1y': (xw, quick), ...}"""
    N = len(C); last = 0; xs = []
    for t in range(N):
        if np.isnan(ma[t]): continue
        d = C[t] - ma[t]; s = 1 if d > SV * atr[t] else (-1 if d < -SV * atr[t] else 0)
        if s:
            if last and s != last: xs.append(t)
            last = s
    out = {}
    for nm, W in YEARS:
        lo = max(N - W, 0); xw = [t for t in xs if t >= lo]
        out[nm] = (len(xw), sum(1 for i, t in enumerate(xs) if t >= lo and i + 1 < len(xs) and xs[i + 1] - t <= 5))
    return out

def raw_row(m, cc=None):
    """m：metrics 表中某一條均線的一列（Series／dict）。cc：cross_counts 的結果（可省略；省略時快敗率不附 n）。回傳顯示用 dict"""
    g = lambda k: m[k] if k in m else np.nan
    wr, wn = wick_ratio(g('A_wick@252'), g('A_raw_n@252'))
    row = {'突破成功率': fmt_rate(g('A_raw@252'), g('A_raw_n@252')), '二日成功率': fmt_rate(g('A_d2@252'), g('A_d2_n@252')), '回測成功率': fmt_rate(g('A_rt@252'), g('A_rt_n@252')),
           '假突破比例': fmt_rate(wr, wn) if wn else '— (n=0)', '假突破次數': int(g('A_wick@252')) if _ok(g('A_wick@252')) else 0, '突破次數(已判定)': int(g('A_raw_n@252')) if _ok(g('A_raw_n@252')) else 0,
           '糾結次數/年(1y/2y/3y)': fmt_triplet([g(f'tg4_{y}') for y, _ in YEARS], fmt_freq), '穿插日/年(1y/2y/3y)': fmt_triplet([g(f'qday_{y}') for y, _ in YEARS], lambda v: fmt_freq(v, 1))}
    qf = []
    for y, _ in YEARS:
        v = g(f'quickfail_{y}')
        qf.append(fmt_rate(v, cc[y][0]) if cc else ('—' if not _ok(v) else f'{v * 100:.1f}%'))
    row['快敗率(1y/2y/3y)'] = ' / '.join(qf)
    return row
