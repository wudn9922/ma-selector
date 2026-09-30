"""只用於驗證 regression 流程能跑通的合成資料（不是真實股價，不參與任何真實結果）"""
import numpy as np, pandas as pd, sys
def synth(seed, n=1300):
    r = np.random.default_rng(seed); vol = 0.012 + 0.01 * r.random(); drift = np.cumsum(r.normal(0, .0006, n)) * 0.3
    ret = r.normal(0, vol, n) + np.sin(np.arange(n) / (40 + 30 * r.random())) * .004 + drift * .1
    c = 100 * np.exp(np.cumsum(ret)); o = np.r_[c[0], c[:-1]] * (1 + r.normal(0, .004, n))
    h = np.maximum(o, c) * (1 + np.abs(r.normal(0, vol / 2, n))); l = np.minimum(o, c) * (1 - np.abs(r.normal(0, vol / 2, n)))
    d = pd.bdate_range(end='2026-09-24', periods=n)
    return pd.DataFrame(dict(time=d.strftime('%Y-%m-%d'), open=o, high=h, low=l, close=c, volume=r.integers(1e6, 5e6, n)))
