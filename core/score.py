"""加權分數（composite4）改成「對固定基準（83 檔）算百分位」
每項指標先轉成「越大越好」的特徵值 → 在基準中的百分位（平均名次，同 pandas rank(pct=True)）
pct_mode（百分位對誰比）：
  'period'（production 預設）：只對基準中「同一條均線週期」的列（83 個值）。長均線本來就穿越少，混在一起比會讓長均線的穿插／快敗百分位機械性偏高
  'band'：對基準中 |週期差| ≤ PCT_BAND 的列（樣本較多，但 15／110 兩端只有單側鄰居）；只供比較
  'pooled'：對基準所有（股票×均線）列，不分週期＝舊版；只供 regression／凍結證據重現
基準檔格式不變（ticker、period＋特徵欄）"""
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

PCT_MODES = ('period', 'band', 'pooled')
PCT_MODE = 'period'                        # production 預設；舊版＝'pooled'
PCT_BAND = 2                               # 'band' 的鄰近週期半徑

def pct_vs(ref_sorted, x):
    left = np.searchsorted(ref_sorted, x, 'left'); right = np.searchsorted(ref_sorted, x, 'right')
    return (left + right + 1) / 2 / len(ref_sorted) * 100

def pct_table(ref, F, cols, pct_mode=PCT_MODE):
    """F（特徵表，含 period）的每個特徵值對基準 ref 的百分位 → {欄: ndarray}；pct_mode 見檔頭"""
    if pct_mode == 'pooled': return {c: pct_vs(np.sort(ref[c].to_numpy(float)), F[c].to_numpy(float)) for c in cols}
    if pct_mode not in PCT_MODES: raise ValueError(f'pct_mode 必須是 {PCT_MODES}，得到 {pct_mode!r}')
    w = 0 if pct_mode == 'period' else PCT_BAND; rp = ref['period'].to_numpy(); fp = F['period'].to_numpy()
    out = {c: np.empty(len(F)) for c in cols}
    for p in np.unique(fp):
        m = np.abs(rp - p) <= w; i = fp == p
        if not m.any(): raise ValueError(f'基準沒有週期 {p} 附近的列（pct_mode={pct_mode!r}）')
        for c in cols: out[c][i] = pct_vs(np.sort(ref[c].to_numpy(float)[m]), F[c].to_numpy(float)[i])
    return out

def normalize_ws(ws):
    return {k: {a: b / sum(w.values()) for a, b in w.items()} for k, w in ws.items()}

def score_table(M, ref, ws=None, pct_mode=PCT_MODE):
    ws = normalize_ws(ws or WS); F = make_features(M); P = M[['period']].copy()
    pr = pct_table(ref, F, FEATS, pct_mode)
    for k in ('突破', '二日', '回測', '雜訊'): P['p' + k] = pr[k]
    for y in ('1y', '2y', '3y'):
        P[f'p穿插_{y}'] = (pr[f'tg_{y}'] + pr[f'qd_{y}']) / 2; P[f'p快敗_{y}'] = pr[f'快敗_{y}']
    med = {k: (ws['短'].get(k, 0) + ws['長'].get(k, 0)) / 2 for k in set(ws['短']) | set(ws['長'])}
    def comp(w, y):
        return sum(v * (P[f'p穿插_{y}'] if k == '穿插' else (P[f'p快敗_{y}'] if k == '快敗' else P['p' + k])) for k, v in w.items())
    P['分數_短'] = comp(ws['短'], '1y'); P['分數_長'] = comp(ws['長'], '3y'); P['分數_中'] = comp(med, '2y')
    P['分數'] = np.where(P.period <= 33, P['分數_短'], np.where(P.period <= 45, P['分數_中'], P['分數_長']))
    return P
