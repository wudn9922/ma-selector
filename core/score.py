"""加權分數（composite4）改成「對固定基準（83 檔）算百分位」
每項指標先轉成「越大越好」的特徵值 → 在基準所有（股票×均線）中的百分位（平均名次，同 pandas rank(pct=True)）
"""
import numpy as np, pandas as pd
WS = {'短': {'突破': .25, '二日': .20, '回測': .15, '雜訊': .15, '穿插': .25},
      '長': {'快敗': .50, '穿插': .50}}
FEATS = ['突破', '二日', '回測', '雜訊'] + [f'{k}_{y}' for k in ('tg', 'qd', '快敗') for y in ('1y', '2y', '3y')]

def wlb(p, n, z=1.0):
    p = np.nan_to_num(np.asarray(p, float)); n = np.maximum(np.nan_to_num(np.asarray(n, float)), 1e-9)
    return (p + z * z / (2 * n) - z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)

def make_features(M):
    """M：metrics 表 → 特徵表（都是越大越好；成功率用 Wilson 下界）"""
    F = M[[c for c in ('ticker', 'period') if c in M.columns]].copy()
    F['突破'] = wlb(M['A_raw@252'], M['A_raw_n@252']); F['二日'] = wlb(M['A_d2@252'], M['A_d2_n@252'])
    F['回測'] = wlb(M['A_rt@252'], M['A_rt_n@252'])
    F['雜訊'] = -(M['A_wick@252'] / (M['A_wick@252'] + M['A_raw_n@252']).clip(lower=1))
    for y in ('1y', '2y', '3y'):
        F[f'tg_{y}'] = -M[f'tg4_{y}']; F[f'qd_{y}'] = -M[f'qday_{y}']; F[f'快敗_{y}'] = -M[f'quickfail_{y}']
    return F

def pct_vs(ref_sorted, x):
    left = np.searchsorted(ref_sorted, x, 'left'); right = np.searchsorted(ref_sorted, x, 'right')
    return (left + right + 1) / 2 / len(ref_sorted) * 100

def normalize_ws(ws):
    return {k: {a: b / sum(w.values()) for a, b in w.items()} for k, w in ws.items()}

def score_table(M, ref, ws=None):
    ws = normalize_ws(ws or WS); F = make_features(M); P = M[['period']].copy()
    R = {c: np.sort(ref[c].to_numpy(float)) for c in FEATS}
    pr = {c: pct_vs(R[c], F[c].to_numpy(float)) for c in FEATS}
    for k in ('突破', '二日', '回測', '雜訊'): P['p' + k] = pr[k]
    for y in ('1y', '2y', '3y'):
        P[f'p穿插_{y}'] = (pr[f'tg_{y}'] + pr[f'qd_{y}']) / 2; P[f'p快敗_{y}'] = pr[f'快敗_{y}']
    med = {k: (ws['短'].get(k, 0) + ws['長'].get(k, 0)) / 2 for k in set(ws['短']) | set(ws['長'])}
    def comp(w, y):
        return sum(v * (P[f'p穿插_{y}'] if k == '穿插' else (P[f'p快敗_{y}'] if k == '快敗' else P['p' + k])) for k, v in w.items())
    P['分數_短'] = comp(ws['短'], '1y'); P['分數_長'] = comp(ws['長'], '3y'); P['分數_中'] = comp(med, '2y')
    P['分數'] = np.where(P.period <= 33, P['分數_短'], np.where(P.period <= 45, P['分數_中'], P['分數_長']))
    return P
