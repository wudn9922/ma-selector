"""實驗選線 v2 的分數（experiments/selector_v2/SPEC.md）：短期公式 × 三個視窗（1y=252、2y=504、3y=756），production 的 score.py 不動
特徵：突破／二日／回測／雜訊（各視窗，與 score.make_features 的 @252 版同式）＋ tg_*／qd_*；百分位對 data/reference_v2.parquet（pct_vs 同現行）
分數_w ＝ score.WS['短'] 加權和（突破、二日、回測、雜訊、穿插＝(tg 百分位＋qd 百分位)/2）"""
import numpy as np, pandas as pd
from .score import wlb, pct_vs, normalize_ws, WS
WINDOWS = (('1y', 252), ('2y', 504), ('3y', 756))
BASE = ('突破', '二日', '回測', '雜訊')
FEATS_V2 = [f'{k}_{y}' for y, _ in WINDOWS for k in BASE] + [f'{k}_{y}' for k in ('tg', 'qd') for y, _ in WINDOWS]

def make_features_v2(M):
    """M：metrics 表（需含 @756）→ 特徵表（越大越好；成功率用 Wilson 下界）"""
    F = M[[c for c in ('ticker', 'period') if c in M.columns]].copy()
    for y, W in WINDOWS:
        F[f'突破_{y}'] = wlb(M[f'A_raw@{W}'], M[f'A_raw_n@{W}']); F[f'二日_{y}'] = wlb(M[f'A_d2@{W}'], M[f'A_d2_n@{W}'])
        F[f'回測_{y}'] = wlb(M[f'A_rt@{W}'], M[f'A_rt_n@{W}'])
        F[f'雜訊_{y}'] = -(M[f'A_wick@{W}'] / (M[f'A_wick@{W}'] + M[f'A_raw_n@{W}']).clip(lower=1))
    for y, _ in WINDOWS: F[f'tg_{y}'] = -M[f'tg4_{y}']; F[f'qd_{y}'] = -M[f'qday_{y}']
    return F

def score_table_v2(M, ref_v2, ws=None):
    """回傳每個 period 的各視窗成分百分位（p突破_y…p穿插_y）與 分數_1y／分數_2y／分數_3y"""
    w = normalize_ws(ws or WS)['短']; F = make_features_v2(M); P = M[['period']].copy()
    pr = {c: pct_vs(np.sort(ref_v2[c].to_numpy(float)), F[c].to_numpy(float)) for c in FEATS_V2}
    for y, _ in WINDOWS:
        for k in BASE: P[f'p{k}_{y}'] = pr[f'{k}_{y}']
        P[f'p穿插_{y}'] = (pr[f'tg_{y}'] + pr[f'qd_{y}']) / 2
        P[f'分數_{y}'] = sum(v * (P[f'p穿插_{y}'] if k == '穿插' else P[f'p{k}_{y}']) for k, v in w.items())
    return P
