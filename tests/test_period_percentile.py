"""同週期百分位（score.pct_mode）與區間內平滑（select.smooth_mode）的測試；合成股價＋repo 的 reference.parquet，不連 Yahoo。
1) pct_table：'period' 只對同週期的基準列、'band' 對 |週期差| ≤ PCT_BAND 的列（兩端單側）、'pooled' 對全部列＝舊版；都等於手算（pandas rank 平均名次）
2) 'period' 只看同週期：改掉某一週期的基準列，只有那個週期的分數會變；pooled 則全部都變
3) 基準池自己打分：period 模式下每個週期的平均百分位／平均分數完全相同（(n+1)/2n）；pooled 模式下長均線的穿插百分位機械性偏高（這次要修的問題）
4) smoothed_scores：'range' 三個區間各自平滑（33/34、45/46 不互相混）、兩端補自己；'whole'＝舊版整條平滑
5) 預設＝新版：score_table／score_table_v2／select／suitability／standardize／recommend 不帶參數時＝pct_mode='period'＋smooth_mode='range'；LEGACY 釘在 whole
6) 非法參數 → ValueError；基準缺某週期 → ValueError；reference.parquet 欄位格式不變
用法：python tests/test_period_percentile.py"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, metrics, score, score_v2 as sv2, select as sel, select_v2 as sv, standardize as sd
from core.recommend import recommend
REF = pd.read_parquet(ROOT / 'data/reference.parquet'); REF2 = pd.read_parquet(ROOT / 'data/reference_v2.parquet')
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
_M = {}
def M_of(seed):
    if seed not in _M: _M[seed] = metrics.compute_metrics(data.normalize(synth(seed, 1300)))
    return _M[seed]
def rank_pct(pool, x):
    """手算：x 加進 pool 後的 pandas 平均名次百分位（同 score.pct_vs）"""
    pool = np.asarray(pool, float); return ((pool < x).sum() + ((pool == x).sum() + 1) / 2) / len(pool) * 100

def test_pct_table_hand():
    F = score.make_features(M_of(3)); rp = REF.period.to_numpy(); n = 0
    for pm, w in (('period', 0), ('band', score.PCT_BAND), ('pooled', None)):
        pr = score.pct_table(REF, F, score.FEATS, pm)
        for i in (0, 1, 2, 18, 19, 30, 31, 60, 93, 94, 95):              # 含 15、16、17、33、34、45、46、108、109、110
            p = int(F.period.iloc[i]); rows = np.ones(len(REF), bool) if w is None else np.abs(rp - p) <= w
            for c in score.FEATS:
                assert abs(pr[c][i] - rank_pct(REF[c].to_numpy(float)[rows], F[c].iloc[i])) < 1e-9, (pm, p, c); n += 1
        if pm == 'period': check(all(int(((np.abs(rp - p)) <= 0).sum()) == 83 for p in range(15, 111)), 'period：每個週期正好 83 個基準值')
    check(n == 3 * 11 * len(score.FEATS), f'pct_table 三種模式 × 11 個週期 × {len(score.FEATS)} 個特徵 ＝ 手算（{n} 格）')
    b = lambda p: sorted(set(rp[np.abs(rp - p) <= score.PCT_BAND].tolist()))
    check(score.PCT_BAND == 2 and b(15) == [15, 16, 17] and b(16) == [15, 16, 17, 18] and b(60) == [58, 59, 60, 61, 62] and b(110) == [108, 109, 110], f'band：15→{b(15)}、60→{b(60)}、110→{b(110)}（兩端單側）')

def test_period_only_uses_same_period():
    M = M_of(11); A = score.score_table(M, REF); Ap = score.score_table(M, REF, pct_mode='pooled')
    R2 = REF.copy(); k = R2.period == 60
    for c in score.FEATS: R2.loc[k, c] = R2.loc[k, c].to_numpy() * 0 + 1e6       # 週期 60 的基準值全部改成極大
    B = score.score_table(M, R2); Bp = score.score_table(M, R2, pct_mode='pooled'); ch = (A['分數'] != B['分數']).to_numpy()
    check(set(A.period[ch]) == {60}, f'period：只有週期 60 的分數改變（改變的週期 {sorted(set(A.period[ch]))}）')
    check((Ap['分數'] != Bp['分數']).mean() > 0.9, f"pooled：改週期 60 的基準 → {(Ap['分數'] != Bp['分數']).mean():.0%} 的週期分數都變（舊版會互相影響）")
    Bb = score.score_table(M, R2, pct_mode='band'); chb = sorted(set(A.period[(score.score_table(M, REF, pct_mode='band')['分數'] != Bb['分數']).to_numpy()]))
    check(chb == [58, 59, 60, 61, 62], f'band：只有 58–62 改變（{chb}）')

def test_reference_self_flat():
    S = sd.scores_from_features(REF, REF); m = S.groupby('period')[['p突破', 'p穿插_1y', 'p快敗_3y', '分數', '分數_短', '分數_中', '分數_長']].mean(); flat = (83 + 1) / (2 * 83) * 100
    check(np.allclose(m.to_numpy(), flat, atol=1e-9), f'period：基準池自己打分，每個週期每個成分與分數的平均都＝{flat:.3f}（沒有週期趨勢）')
    P = sd.scores_from_features(REF, REF, pct_mode='pooled').groupby('period').mean(numeric_only=True)
    check(P.loc[110, 'p穿插_1y'] - P.loc[15, 'p穿插_1y'] > 40 and P.loc[110, '分數'] - P.loc[46, '分數'] > 15,
          f"pooled（舊版）：平均穿插百分位 MA15 {P.loc[15, 'p穿插_1y']:.1f} → MA110 {P.loc[110, 'p穿插_1y']:.1f}；長期平均分數 MA46 {P.loc[46, '分數']:.1f} → MA110 {P.loc[110, '分數']:.1f}（差距 > gap 15）")
    B = sd.scores_from_features(REF, REF, pct_mode='band').groupby('period')['分數'].mean()
    bs, ps = B.max() - B.min(), P['分數'].max() - P['分數'].min()   # 絕對值會隨每月重建的基準浮動（2.7→3.4），所以和 pooled 的週期趨勢比
    check(bs < ps / 4, f'band：基準池平均分數全部週期在 {B.min():.1f}–{B.max():.1f}（範圍 {bs:.1f}，不到 pooled {ps:.1f} 的四分之一）')

def test_range_smoothing():
    S = score.score_table(M_of(29), REF); S = S.sort_values('period'); s = S['分數'].to_numpy(); P = S['period'].to_numpy()
    Pr, r = sel.smoothed_scores(S); Pw, w = sel.smoothed_scores(S, 'whole'); at = lambda p: s[p - 15]
    check(np.array_equal(Pr, P) and np.array_equal(w, sel.smooth(s)), "whole＝舊版 smooth(整條 15–110)")
    exp = {15: (2 * at(15) + at(16)) / 3, 24: (at(23) + at(24) + at(25)) / 3, 33: (at(32) + 2 * at(33)) / 3, 34: (2 * at(34) + at(35)) / 3, 45: (at(44) + 2 * at(45)) / 3, 46: (2 * at(46) + at(47)) / 3, 110: (at(109) + 2 * at(110)) / 3}
    check(all(abs(r[p - 15] - v) < 1e-12 for p, v in exp.items()), 'range：33／34／45／46 兩端補自己，不混到另一個公式的分數；15、110 同舊版')
    S2 = S.copy(); S2.loc[(S2.period >= 34) & (S2.period <= 45), '分數'] += 50; _, r2 = sel.smoothed_scores(S2); _, w2 = sel.smoothed_scores(S2, 'whole')
    out = (P < 34) | (P > 45)
    check(np.array_equal(r[out], r2[out]) and not np.array_equal(w[out], w2[out]), 'range：改中期分數不影響短期／長期的平滑分數（whole 會影響 33、46）')
    for nm, lo, hi, _ in sel.RANGES:
        m = (P >= lo) & (P <= hi); assert np.array_equal(r[m], sel.smooth(s[m]))
    check(True, 'range：每個區間＝該區間自己的 smooth()')

def test_select_uses_range_scores():
    df = data.normalize(synth(41, 1300)); S = score.score_table(metrics.compute_metrics(df), REF); P, Ss = sel.smoothed_scores(S); sm = dict(zip(P.tolist(), Ss.tolist()))
    R = sel.select(df, S)
    for nm, lo, hi, _ in sel.RANGES:
        c = R[nm]['cands']; best = max(v for p, v in sm.items() if lo <= p <= hi)
        assert all(x['結構分'] == sm[x['均線']] and lo <= x['均線'] <= hi and x['結構分'] >= best - sel.GAP for x in c) and R[nm]['best'] == round(best, 1)
    check(True, '候選的結構分＝區間內平滑分數、與區間最高差 ≤ gap、best＝區間最高（新版預設）')
    su = sel.suitability(S); check(su == (max(v for p, v in sm.items() if p <= 33), max(v for p, v in sm.items() if p >= 46)), 'suitability 用區間內平滑')

def test_defaults_are_new_mode():
    check(score.PCT_MODE == 'period' and score.PCT_MODES == ('period', 'band', 'pooled') and sel.SMOOTH_MODE == 'range' and sel.SMOOTH_MODES == ('range', 'whole'), 'production 預設：pct_mode=period、smooth_mode=range')
    check(sel.LEGACY == dict(gap=15, method='bt', longonly=True, smooth_mode='whole'), 'LEGACY 釘在整條平滑（分數表要配 pct_mode=pooled）')
    df = data.normalize(synth(42)); M = metrics.compute_metrics(df)
    Sn, So = score.score_table(M, REF, pct_mode='period'), score.score_table(M, REF, pct_mode='pooled')
    check(score.score_table(M, REF).equals(Sn) and not Sn.equals(So), 'score_table 預設＝period（≠ pooled）')
    T = sv2.score_table_v2(M, REF2); check(T.equals(sv2.score_table_v2(M, REF2, pct_mode='period')) and not T.equals(sv2.score_table_v2(M, REF2, pct_mode='pooled')), 'score_table_v2 預設＝period')
    Rn = sel.select(df, Sn, smooth_mode='range'); r = recommend(df, REF, 'T')
    check([g['final'] for g in r['ranges']] == [Rn[nm]['final'] for nm, *_ in sel.RANGES] and [[c['period'] for c in g['candidates']] for g in r['ranges']] == [[c['均線'] for c in Rn[nm]['cands']] for nm, *_ in sel.RANGES],
          f"recommend()（不改 recommend.py）＝ select(score_table(period), range)：{[g['final'] for g in r['ranges']]}")
    check(r['suitability'] == dict(short=round(sel.suitability(Sn, 'range')[0], 1), long=round(sel.suitability(Sn, 'range')[1], 1)), 'recommend 的 suitability 用新版')
    check(sd.range_bests(Sn) == sd.range_bests(Sn, 'range') and sd.ref_stock_bests(REF).equals(sd.ref_stock_bests(REF, pct_mode='period', smooth_mode='range')), 'standardize 預設＝period＋range')
    V = sv.select_v2(df, M, REF2); check(V['短期']['final1'] == sv.select_v2(df, M, REF2, pct_mode='period')['短期']['final1'], 'select_v2 預設＝period')
    O = sel.select(df, So, smooth_mode='whole'); print(f"# 這檔 old→new final：{[O[nm]['final'] for nm, *_ in sel.RANGES]} → {[Rn[nm]['final'] for nm, *_ in sel.RANGES]}")

def test_invalid_and_format():
    F = score.make_features(M_of(3))
    for f in (lambda: score.pct_table(REF, F, score.FEATS, 'same'), lambda: score.score_table(M_of(3), REF, pct_mode='Period'), lambda: sel.smoothed_scores(score.score_table(M_of(3), REF), 'within'),
              lambda: score.score_table(M_of(3), REF[REF.period != 50]), lambda: score.score_table(M_of(3), REF[(REF.period < 48) | (REF.period > 52)], pct_mode='band')):
        try: f()
        except ValueError: continue
        check(False, '應該 ValueError')
    check(True, '非法 pct_mode／smooth_mode、基準缺週期（period／band）→ ValueError')
    check(len(score.score_table(M_of(3), REF[REF.period != 50], pct_mode='pooled')) == 96, 'pooled 不需要每個週期都有基準列（舊版行為）')
    check(list(REF.columns[:2]) == ['ticker', 'period'] and sorted(REF.columns[2:]) == sorted(score.FEATS) and len(REF) == 83 * 96 and list(REF2.columns[:2]) == ['ticker', 'period'] and sorted(REF2.columns[2:]) == sorted(sv2.FEATS_V2),'reference.parquet／reference_v2.parquet 欄位格式不變（ticker、period＋特徵）')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_') and callable(v): print('#', k); v()
    print('ALL PASS')
