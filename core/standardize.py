"""股票層級排名（display-only）：這檔股票的「區間最高分（平滑後）」在基準 83 檔各自的區間最高分中排第幾（百分位，同 score.pct_vs，同分算一半）
只用來顯示，不參與任何選線、分數。
scores_from_features* ＝ score_table／score_table_v2 的算式搬過來，但輸入是特徵表 F（reference*.parquet 的列）而不是 metrics 表 M，所以基準股票可以直接拿自己的特徵列去對整個基準打分
pct_mode／smooth_mode 與 score.score_table／select.smoothed_scores 相同（預設＝production：同週期百分位、區間內平滑；'pooled'／'whole'＝舊版）"""
import numpy as np, pandas as pd
from . import select as sel, select_v2 as sv2
from .score import WS, FEATS, pct_vs, pct_table, normalize_ws, PCT_MODE
from .score_v2 import WINDOWS, BASE, FEATS_V2

def scores_from_features(F, ref, ws=None, pct_mode=PCT_MODE):
    """同 score.score_table(M, ref, ws, pct_mode)，F ＝ score.make_features(M)（欄位：period＋FEATS）"""
    ws = normalize_ws(ws or WS); P = F[['period']].copy()
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

def scores_v2_from_features(F, ref_v2, ws=None, pct_mode=PCT_MODE):
    """同 score_v2.score_table_v2(M, ref_v2, ws, pct_mode)，F ＝ score_v2.make_features_v2(M)"""
    w = normalize_ws(ws or WS)['短']; P = F[['period']].copy()
    pr = pct_table(ref_v2, F, FEATS_V2, pct_mode)
    for y, _ in WINDOWS:
        for k in BASE: P[f'p{k}_{y}'] = pr[f'{k}_{y}']
        P[f'p穿插_{y}'] = (pr[f'tg_{y}'] + pr[f'qd_{y}']) / 2
        P[f'分數_{y}'] = sum(v * (P[f'p穿插_{y}'] if k == '穿插' else P[f'p{k}_{y}']) for k, v in w.items())
    return P

def range_bests(S, smooth_mode=sel.SMOOTH_MODE):
    """一檔股票的分數表 S（score_table 輸出）→ {'短期','中期','長期': 區間最高分（平滑同 select.smoothed_scores(S, smooth_mode)；邊界同 select.RANGES）}"""
    P, Ss = sel.smoothed_scores(S, smooth_mode)
    return {nm: float(Ss[(P >= lo) & (P <= hi)].max()) for nm, lo, hi, _w in sel.RANGES}

def range_bests_v2(T):
    """T ＝ score_table_v2 輸出 → dict(short_2y, short_1y, mid_3y)（平滑後；短期 15–45、中期 46–70；同 select_v2 suitability）"""
    def best(y, lo, hi):
        P, s = sv2.smoothed_v2(T, y); return float(s[(P >= lo) & (P <= hi)].max())
    return dict(short_2y=best('2y', *sv2.SHORT), short_1y=best('1y', *sv2.SHORT), mid_3y=best('3y', *sv2.MID))

def ref_stock_bests(ref, ws=None, pct_mode=PCT_MODE, smooth_mode=sel.SMOOTH_MODE):
    """基準每檔股票的區間最高分 → DataFrame(ticker, 短期, 中期, 長期)。一次對整個基準打分（百分位只算一次），再依 ticker 分組平滑；
    每列的百分位只和該列自己的特徵（與週期）有關，所以等於「每檔各自 scores_from_features(該檔列, ref, ws, pct_mode)」"""
    ref = ref.reset_index(drop=True); S = scores_from_features(ref, ref, ws, pct_mode); S['ticker'] = ref['ticker'].to_numpy()
    return pd.DataFrame([{'ticker': t, **range_bests(g, smooth_mode)} for t, g in S.groupby('ticker', sort=False)])

def ref_stock_bests_v2(ref_v2, ws=None, pct_mode=PCT_MODE):
    """v2 基準每檔股票的 short_2y／short_1y／mid_3y（平滑後區間最高分）→ DataFrame(ticker, short_2y, short_1y, mid_3y)"""
    ref_v2 = ref_v2.reset_index(drop=True); T = scores_v2_from_features(ref_v2, ref_v2, ws, pct_mode); T['ticker'] = ref_v2['ticker'].to_numpy()
    return pd.DataFrame([{'ticker': t, **range_bests_v2(g)} for t, g in T.groupby('ticker', sort=False)])

def rank_pct(values, x):
    """x 在基準值 values 中的百分位（同 score.pct_vs，同分算一半；上限封頂 100）→ (百分位, n)；values 的 NaN 不算"""
    v = np.asarray(values, float); v = v[~np.isnan(v)]
    if len(v) == 0 or x != x: return float('nan'), len(v)
    return min(float(pct_vs(np.sort(v), x)), 100.0), len(v)   # pct_vs 對「高於基準全部」的 x 會超過 100（平均名次 n+0.5），顯示用封頂 100
