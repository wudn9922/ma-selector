"""突破幅度實驗（experiments/selector_v2/MAGNITUDE_SPEC.md）：在現行分數與 v2 分數上多加一項「幅度」，production 的 score.py／score_v2.py 不動
幅度＝突破進場持倉的最大有利幅度÷ATR 的中位數（metrics 的 mfe_med@W；沒有突破＝NaN→0）；越大越好
現行實驗版：score_table_mag＝score.score_table 同算法，短期與中期多一項幅度（@252）；v2 實驗版：score_table_v2_mag＝score_v2.score_table_v2 每視窗多一項 幅度_{1y,2y,3y}
百分位基準＝data/reference_mag.parquet（含現行＋v2＋幅度全部特徵）；w_mag=0 時與原分數表逐位元組相同（多一欄 p幅度）"""
import numpy as np, pandas as pd
from .score import WS, FEATS, make_features, pct_vs, normalize_ws
from .score_v2 import WINDOWS, BASE, FEATS_V2, make_features_v2
W_MAG = .20                                                 # 幅度權重預設（網頁滑桿可調）
WS_MAG = {'短': {'突破': .20, '二日': .16, '回測': .12, '雜訊': .12, '穿插': .20, '幅度': W_MAG}, '長': WS['長']}   # ＝WS['短'] ×0.8 ＋幅度 .20；長期不加幅度
FEATS_MAG = FEATS + ['幅度']
FEATS_V2_MAG = FEATS_V2 + [f'幅度_{y}' for y, _ in WINDOWS]
FEATS_ALL_MAG = FEATS + [c for c in FEATS_V2 if c not in FEATS] + ['幅度'] + [f'幅度_{y}' for y, _ in WINDOWS]   # reference_mag 的特徵欄（無重複）

def make_features_mag(M):
    """M：metrics 表（需含 mfe_med@252／504／756）→ make_features 的特徵＋幅度（＝幅度_1y）＋幅度_1y／2y／3y（NaN→0）"""
    F = make_features(M)
    for y, W in WINDOWS: F[f'幅度_{y}'] = M[f'mfe_med@{W}'].fillna(0.).to_numpy(float)
    F['幅度'] = F['幅度_1y']; return F

def mag_ws(ws=None, w_mag=W_MAG):
    """使用者的短期權重正規化後縮放到合計 1−w_mag，再加 幅度＝w_mag（已正規化，不要再 normalize）；長期不變。w_mag=0 時短期權重逐位元組同 normalize_ws"""
    n = normalize_ws(ws or WS); s = {k: v * (1 - w_mag) for k, v in n['短'].items() if k != '幅度'}; s['幅度'] = w_mag
    return {'短': s, '長': n['長']}

def score_table_mag(M, ref_mag, ws=None, w_mag=W_MAG):
    """同 score.score_table（短期 1y、中期＝短長平均權重 2y、長期 3y），短期與中期多一項 幅度（@252；中期權重＝(w_mag＋0)/2）"""
    wm = mag_ws(ws, w_mag); F = make_features_mag(M); P = M[['period']].copy()
    R = {c: np.sort(ref_mag[c].to_numpy(float)) for c in FEATS_MAG}
    pr = {c: pct_vs(R[c], F[c].to_numpy(float)) for c in FEATS_MAG}
    for k in ('突破', '二日', '回測', '雜訊'): P['p' + k] = pr[k]
    P['p幅度'] = pr['幅度']                          # comp 用；輸出時移到最後一欄，其餘欄位與順序同 score_table
    for y in ('1y', '2y', '3y'):
        P[f'p穿插_{y}'] = (pr[f'tg_{y}'] + pr[f'qd_{y}']) / 2; P[f'p快敗_{y}'] = pr[f'快敗_{y}']
    w5 = {k: v for k, v in wm['短'].items() if k != '幅度'}                       # 不含幅度的短期權重：用 set(dict) 取鍵，迭代順序才會和 score_table 一樣（浮點加總順序相同 → w_mag=0 逐位元組相同），幅度放最後
    base = {k: (wm['短'].get(k, 0) + wm['長'].get(k, 0)) / 2 for k in set(w5) | set(wm['長'])}
    med = dict(base); med['幅度'] = (wm['短']['幅度'] + 0) / 2
    def comp(w, y):
        return sum(v * (P[f'p穿插_{y}'] if k == '穿插' else (P[f'p快敗_{y}'] if k == '快敗' else P['p' + k])) for k, v in w.items())
    P['分數_短'] = comp(wm['短'], '1y'); P['分數_長'] = comp(wm['長'], '3y'); P['分數_中'] = comp(med, '2y')
    P['分數'] = np.where(P.period <= 33, P['分數_短'], np.where(P.period <= 45, P['分數_中'], P['分數_長']))
    P['p幅度'] = P.pop('p幅度'); return P

def score_table_v2_mag(M, ref_mag, ws=None, w_mag=W_MAG):
    """同 score_v2.score_table_v2（短期公式 × 三視窗），每視窗多一項 幅度_{y}；回傳多 p幅度_{y} 欄"""
    w = mag_ws(ws, w_mag)['短']; F = make_features_v2(M); Fm = make_features_mag(M); P = M[['period']].copy()
    pr = {c: pct_vs(np.sort(ref_mag[c].to_numpy(float)), F[c].to_numpy(float)) for c in FEATS_V2}
    for y, _ in WINDOWS: pr[f'幅度_{y}'] = pct_vs(np.sort(ref_mag[f'幅度_{y}'].to_numpy(float)), Fm[f'幅度_{y}'].to_numpy(float))
    for y, _ in WINDOWS:
        for k in BASE + ('幅度',): P[f'p{k}_{y}'] = pr[f'{k}_{y}']
        P[f'p穿插_{y}'] = (pr[f'tg_{y}'] + pr[f'qd_{y}']) / 2
        P[f'分數_{y}'] = sum(v * (P[f'p穿插_{y}'] if k == '穿插' else P[f'p{k}_{y}']) for k, v in w.items())
    return P
