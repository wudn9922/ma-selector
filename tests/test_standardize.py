"""股票層級排名（core/standardize.py，display-only）的測試
1) scores_from_features(make_features(M), ref) ＝ score.score_table(M, ref)（DataFrame.equals，預設與自訂權重）；v2 同
2) ref_stock_bests／ref_stock_bests_v2：每檔的值等於手算（逐檔打分＋平滑＋區間最大）；一次打分 ＝ 逐檔
3) rank_pct：範圍、同分、單調
4) production 不變：score.py／select.py 與 474d8f6 逐位元組相同
用法：python tests/test_standardize.py"""
import subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, score, score_v2 as sv2, metrics, select as sel, select_v2 as sv, standardize as sd
REF = pd.read_parquet(ROOT / 'data/reference.parquet'); REF2 = pd.read_parquet(ROOT / 'data/reference_v2.parquet'); SEEDS = (3, 11, 29)
WS_CUSTOM = {'短': {'突破': 40, '二日': 10, '回測': 5, '雜訊': 20, '穿插': 25}, '長': {'快敗': 30, '穿插': 70}}
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
_M = {}
def M_of(seed):
    if seed not in _M: _M[seed] = metrics.compute_metrics(data.normalize(synth(seed, 1300)))
    return _M[seed]

def test_scores_from_features_equal():
    for seed in SEEDS:
        M = M_of(seed)
        for nm, ws in (('預設', None), ('自訂權重', WS_CUSTOM)):
            A = score.score_table(M, REF, ws); B = sd.scores_from_features(score.make_features(M), REF, ws)
            check(list(A.columns) == list(B.columns) and A.equals(B) and all(A[c].to_numpy().tobytes() == B[c].to_numpy().tobytes() for c in A.columns), f'seed {seed}（{nm}）：scores_from_features ＝ score_table（逐位元組）')
            A2 = sv2.score_table_v2(M, REF2, ws); B2 = sd.scores_v2_from_features(sv2.make_features_v2(M), REF2, ws)
            check(list(A2.columns) == list(B2.columns) and A2.equals(B2) and all(A2[c].to_numpy().tobytes() == B2[c].to_numpy().tobytes() for c in A2.columns), f'seed {seed}（{nm}）：scores_v2_from_features ＝ score_table_v2（逐位元組）')

def manual_bests(t, ref, ws):
    S = sd.scores_from_features(ref[ref.ticker == t], ref, ws); P, Ss = sel.smoothed_scores(S)
    return {nm: float(Ss[(P >= lo) & (P <= hi)].max()) for nm, lo, hi, _w in (('短期', 15, 33, 0), ('中期', 34, 45, 0), ('長期', 46, 110, 0))}
def manual_bests_v2(t, ref2, ws):
    T = sd.scores_v2_from_features(ref2[ref2.ticker == t], ref2, ws).sort_values('period'); P = T['period'].to_numpy(); f = lambda y, lo, hi: float(sel.smooth(T[f'分數_{y}'].to_numpy())[(P >= lo) & (P <= hi)].max())
    return dict(short_2y=f('2y', 15, 45), short_1y=f('1y', 15, 45), mid_3y=f('3y', 46, 70))

def test_ref_stock_bests():
    tks = list(REF.ticker.unique()); pick = [tks[0], tks[17], tks[41], tks[-1]]
    check(sel.RANGES[0][1:3] == (15, 33) and sel.RANGES[1][1:3] == (34, 45) and sel.RANGES[2][1:3] == (46, 110), '區間邊界 15–33／34–45／46–110（同 select.RANGES）')
    for nm, ws in (('預設', None), ('自訂權重', WS_CUSTOM)):
        B = sd.ref_stock_bests(REF, ws).set_index('ticker')
        check(len(B) == REF.ticker.nunique() == 83 and list(B.columns) == ['短期', '中期', '長期'] and B.notna().all().all(), f'（{nm}）ref_stock_bests：{len(B)} 檔、欄位 {list(B.columns)}')
        for t in pick:
            m = manual_bests(t, REF, ws); check(all(B.loc[t, k] == m[k] for k in m), f'（{nm}）{t}：區間最高分等於逐檔手算 {({k: round(v, 1) for k, v in m.items()})}')
        # 短期／長期最高分與 sel.suitability（15–33、P>=46）一致
        t = pick[1]; S = sd.scores_from_features(REF[REF.ticker == t], REF, ws); su = sel.suitability(S); check((B.loc[t, '短期'], B.loc[t, '長期']) == su, f'（{nm}）{t}：短期／長期最高分 ＝ select.suitability {su}')
        B2 = sd.ref_stock_bests_v2(REF2, ws).set_index('ticker')
        check(len(B2) == 83 and list(B2.columns) == ['short_2y', 'short_1y', 'mid_3y'] and B2.notna().all().all(), f'（{nm}）ref_stock_bests_v2：{len(B2)} 檔、欄位 {list(B2.columns)}')
        for t in pick:
            m = manual_bests_v2(t, REF2, ws); check(all(B2.loc[t, k] == m[k] for k in m), f'（{nm}）{t}：v2 區間最高分等於逐檔手算 {({k: round(v, 1) for k, v in m.items()})}')
    # 合成股票：range_bests 與 select_v2 suitability 同鍵同值
    T = sv2.score_table_v2(M_of(11), REF2); V = sv.select_v2(data.normalize(synth(11, 1300)), M_of(11), REF2, long_result=None)
    check(sd.range_bests_v2(T) == V['suitability'], f"range_bests_v2 ＝ select_v2 suitability {({k: round(v, 1) for k, v in V['suitability'].items()})}")
    S = score.score_table(M_of(11), REF); r = sd.range_bests(S); su = sel.suitability(S); check((r['短期'], r['長期']) == su, 'range_bests 短期／長期 ＝ select.suitability')

def test_vectorized_equals_per_ticker():
    A = sd.ref_stock_bests(REF).set_index('ticker'); n = 0
    for t in REF.ticker.unique():
        m = manual_bests(t, REF, None); assert all(A.loc[t, k] == m[k] for k in m), t; n += 1
    check(n == 83, f'ref_stock_bests 一次打分 ＝ 逐檔打分（{n} 檔全部逐位元組相同）')
    A2 = sd.ref_stock_bests_v2(REF2).set_index('ticker'); n = 0
    for t in REF2.ticker.unique():
        m = manual_bests_v2(t, REF2, None); assert all(A2.loc[t, k] == m[k] for k in m), t; n += 1
    check(n == 83, f'ref_stock_bests_v2 一次打分 ＝ 逐檔打分（{n} 檔）')
    shuf = REF.sample(frac=1, random_state=0); B = sd.ref_stock_bests(shuf).set_index('ticker').loc[A.index]
    check(B.equals(A), '基準列順序打亂後結果相同')

def test_rank_pct():
    v = np.array([10., 20., 20., 30., 40.]); n = 5
    check(sd.rank_pct(v, 25.) == (70.0, n) and sd.rank_pct(v, 20.) == (50.0, n) and sd.rank_pct(v, 40.) == (100.0, n), 'rank_pct 中間值與同分（同分算一半；平均名次 ÷ n）')
    p_lo, _ = sd.rank_pct(v, -1e9); p_hi, _ = sd.rank_pct(v, 1e9); check(p_lo == 10.0 and p_hi == 100.0 and float(score.pct_vs(np.sort(v), 1e9)) > 100, f'rank_pct 範圍：全低 {p_lo}（pct_vs 平均名次 0.5/n 起跳）、全高 {p_hi}（pct_vs 原值 110 封頂 100）')
    xs = np.linspace(-5, 105, 200); ps = [sd.rank_pct(REF.groupby('ticker')['突破'].max().to_numpy(), x)[0] for x in xs]; check(all(b >= a for a, b in zip(ps, ps[1:])) and all(0 <= p <= 100 for p in ps), 'rank_pct 對 x 單調不減、介於 0–100')
    r = np.random.default_rng(0).normal(size=83); check(sd.rank_pct(r, r[7]) == (float(score.pct_vs(np.sort(r), r[7])), 83) and sd.rank_pct(r[::-1], 0.3) == sd.rank_pct(r, 0.3), 'rank_pct ＝ score.pct_vs(np.sort(values), x)，與順序無關，n=83')
    check(sd.rank_pct(np.array([1., np.nan, 3.]), 2.)[1] == 2 and np.isnan(sd.rank_pct(r, float('nan'))[0]) and np.isnan(sd.rank_pct([], 1.)[0]), 'NaN 基準值不算進 n；x 為 NaN／空基準 → NaN')

def test_production_unchanged():
    # production 的 score.py／select.py 與 474d8f6（v2 實驗開始前的 main）逐位元組相同；v2 檔案由 test_selector_v2／test_magnitude 檢查
    for f in ('core/score.py', 'core/select.py'):
        old = subprocess.run(['git', 'show', f'474d8f6:{f}'], cwd=ROOT, capture_output=True, check=True).stdout
        check((ROOT / f).read_bytes() == old, f'{f} 與 474d8f6 逐位元組相同')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_') and callable(v): print('#', k); v()
    print('ALL PASS')
