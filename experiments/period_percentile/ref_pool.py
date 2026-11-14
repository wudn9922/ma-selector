"""基準池自己對自己打分：各週期平均分數／平均穿插百分位（三種 pct_mode），以及每檔基準股票區間內最高平滑分落點（不需回測）"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
import numpy as np, pandas as pd
from core import select as sel, standardize as sd
OUT = os.path.dirname(os.path.abspath(__file__))
REF = pd.read_parquet(f'{ROOT}/data/reference.parquet').reset_index(drop=True)
MODES = {'OLD': ('pooled', 'whole'), 'NEW_period': ('period', 'range'), 'NEW_band': ('band', 'range')}
rows, tops = [], []
for cfg, (pm, smm) in MODES.items():
    S = sd.scores_from_features(REF, REF, pct_mode=pm); S['ticker'] = REF['ticker'].to_numpy()
    g = S.groupby('period')
    m = g[['分數', '分數_短', '分數_中', '分數_長', 'p穿插_1y', 'p穿插_2y', 'p穿插_3y', 'p快敗_3y', 'p突破']].mean()
    m['config'] = cfg; rows.append(m.reset_index())
    for t, gg in S.groupby('ticker', sort=False):
        P, Ss = sel.smoothed_scores(gg, smm)
        for nm, lo, hi, _ in sel.RANGES:
            k = (P >= lo) & (P <= hi); tops.append(dict(config=cfg, ticker=t, range=nm, top=int(P[k][np.argmax(Ss[k])])))
pd.concat(rows).to_csv(f'{OUT}/ref_mean_by_period.csv', index=False); pd.DataFrame(tops).to_csv(f'{OUT}/ref_top.csv', index=False)
R = pd.concat(rows).set_index(['config', 'period'])
for cfg in MODES:
    print(cfg, {p: round(R.loc[(cfg, p), '分數'], 1) for p in (15, 24, 33, 34, 40, 45, 46, 60, 80, 100, 110)}, ' p穿插_1y', {p: round(R.loc[(cfg, p), 'p穿插_1y'], 1) for p in (15, 33, 45, 110)})
T = pd.DataFrame(tops)
for cfg in MODES:
    for nm, lo, hi, _ in sel.RANGES:
        x = T[(T.config == cfg) & (T.range == nm)].top; print(cfg, nm, f'lo {(x == lo).mean():.2f} hi {(x == hi).mean():.2f} median {x.median()}')
