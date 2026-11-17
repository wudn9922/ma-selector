"""股票層級排名（core/standardize.py，display-only）的測試
1) scores_from_features(make_features(M), ref) ＝ score.score_table(M, ref)（DataFrame.equals，預設與自訂權重）；v2 同
2) ref_stock_bests／ref_stock_bests_v2：每檔的值等於手算（逐檔打分＋平滑＋區間最大）；一次打分 ＝ 逐檔
3) rank_pct：範圍、同分、單調
4) 舊版分數可重現：pct_mode='pooled'＋smooth_mode='whole' 的 score_table／select／suitability／scores_from_features 與 474d8f6 的 score.py／select.py 結果逐位元組相同；
   production 預設（同週期百分位、區間內平滑）的同一組檢查改對 pct_mode='period'／smooth_mode='range' 做
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
            for pm in (None,) + score.PCT_MODES:
                kw = {} if pm is None else dict(pct_mode=pm); tag = f'{nm}，{pm or "預設 pct_mode"}'
                A = score.score_table(M, REF, ws, **kw); B = sd.scores_from_features(score.make_features(M), REF, ws, **kw)
                check(list(A.columns) == list(B.columns) and A.equals(B) and all(A[c].to_numpy().tobytes() == B[c].to_numpy().tobytes() for c in A.columns), f'seed {seed}（{tag}）：scores_from_features ＝ score_table（逐位元組）')
                A2 = sv2.score_table_v2(M, REF2, ws, **kw); B2 = sd.scores_v2_from_features(sv2.make_features_v2(M), REF2, ws, **kw)
                check(list(A2.columns) == list(B2.columns) and A2.equals(B2) and all(A2[c].to_numpy().tobytes() == B2[c].to_numpy().tobytes() for c in A2.columns), f'seed {seed}（{tag}）：scores_v2_from_features ＝ score_table_v2（逐位元組）')

def manual_bests(t, ref, ws, pct_mode=score.PCT_MODE, smooth_mode=sel.SMOOTH_MODE):
    S = sd.scores_from_features(ref[ref.ticker == t], ref, ws, pct_mode); P, Ss = sel.smoothed_scores(S, smooth_mode)
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
    for pm, smm in (('pooled', 'whole'), ('band', 'range')):           # 舊版與鄰近週期版也是「一次打分 ＝ 逐檔」
        A = sd.ref_stock_bests(REF, pct_mode=pm, smooth_mode=smm).set_index('ticker'); n = 0
        for t in REF.ticker.unique():
            m = manual_bests(t, REF, None, pm, smm); assert all(A.loc[t, k] == m[k] for k in m), (pm, t); n += 1
        check(n == 83, f'ref_stock_bests(pct_mode={pm!r}, smooth_mode={smm!r}) 一次打分 ＝ 逐檔打分（{n} 檔）')

def test_rank_pct():
    v = np.array([10., 20., 20., 30., 40.]); n = 5
    check(sd.rank_pct(v, 25.) == (70.0, n) and sd.rank_pct(v, 20.) == (50.0, n) and sd.rank_pct(v, 40.) == (100.0, n), 'rank_pct 中間值與同分（同分算一半；平均名次 ÷ n）')
    p_lo, _ = sd.rank_pct(v, -1e9); p_hi, _ = sd.rank_pct(v, 1e9); check(p_lo == 10.0 and p_hi == 100.0 and float(score.pct_vs(np.sort(v), 1e9)) > 100, f'rank_pct 範圍：全低 {p_lo}（pct_vs 平均名次 0.5/n 起跳）、全高 {p_hi}（pct_vs 原值 110 封頂 100）')
    xs = np.linspace(-5, 105, 200); ps = [sd.rank_pct(REF.groupby('ticker')['突破'].max().to_numpy(), x)[0] for x in xs]; check(all(b >= a for a, b in zip(ps, ps[1:])) and all(0 <= p <= 100 for p in ps), 'rank_pct 對 x 單調不減、介於 0–100')
    r = np.random.default_rng(0).normal(size=83); check(sd.rank_pct(r, r[7]) == (float(score.pct_vs(np.sort(r), r[7])), 83) and sd.rank_pct(r[::-1], 0.3) == sd.rank_pct(r, 0.3), 'rank_pct ＝ score.pct_vs(np.sort(values), x)，與順序無關，n=83')
    check(sd.rank_pct(np.array([1., np.nan, 3.]), 2.)[1] == 2 and np.isnan(sd.rank_pct(r, float('nan'))[0]) and np.isnan(sd.rank_pct([], 1.)[0]), 'NaN 基準值不算進 n；x 為 NaN／空基準 → NaN')

def old_module(name, commit='474d8f6'):
    import types
    src = subprocess.run(['git', 'show', f'{commit}:core/{name}.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType(f'core._{name}_474'); m.__package__ = 'core'; exec(compile(src, f'core/{name}.py@{commit}', 'exec'), m.__dict__)
    if name == 'select': m.bt = old_module('backtest')
    return m

def test_production_unchanged():
    # 原本是「score.py／select.py 與 474d8f6 逐位元組相同」；加入 pct_mode／smooth_mode 後檔案依設計已不同 →
    # 改成：明確指定舊版（pct_mode='pooled'、smooth_mode='whole'）時，結果與 474d8f6 的模組逐位元組相同（含預設與自訂權重、LEGACY、min_period）
    OS, OL = old_module('score'), old_module('select')
    for seed in SEEDS:
        M, df = M_of(seed), data.normalize(synth(seed, 1300))
        for nm, ws in (('預設', None), ('自訂權重', WS_CUSTOM)):
            A, B = score.score_table(M, REF, ws, pct_mode='pooled'), OS.score_table(M, REF, ws)
            check(list(A.columns) == list(B.columns) and A.equals(B) and all(A[c].to_numpy().tobytes() == B[c].to_numpy().tobytes() for c in A.columns), f'seed {seed}（{nm}）：score_table(pct_mode=pooled) 與 474d8f6 逐位元組相同')
            rb = sd.range_bests(A, 'whole'); check(sel.suitability(A, 'whole') == OL.suitability(B) == (rb['短期'], rb['長期']), f'seed {seed}（{nm}）：suitability(whole)／range_bests(whole) 與 474d8f6 相同')
            P0, s0 = OL.smoothed_scores(B); P1, s1 = sel.smoothed_scores(A, 'whole'); check(np.array_equal(P0, P1) and s0.tobytes() == s1.tobytes(), f'seed {seed}（{nm}）：smoothed_scores(whole) 與 474d8f6 逐位元組相同')
        S0 = OS.score_table(M, REF)
        for nm, kw in (('production 規則', dict()), ('LEGACY', dict(gap=15, method='bt', longonly=True)), ('min_period', dict(final_rule='min_period'))):
            new_kw = dict(sel.LEGACY) if nm == 'LEGACY' else dict(kw, smooth_mode='whole', window_mode='legacy_exit')
            o = OL.select(df, S0, **kw); a = sel.select(df, score.score_table(M, REF, pct_mode='pooled'), **new_kw)
            check(a == o, f'seed {seed}：select({nm}，pooled＋whole) 與 474d8f6 相同')   # 474d8f6 的 select.py 已含短期 rescue（＝改動前 HEAD）
    # 新版 production 預設＝同週期百分位＋區間內平滑（同一組 API，結果與明確指定新模式相同）
    M, df = M_of(3), data.normalize(synth(3, 1300))
    check(score.PCT_MODE == 'period' and sel.SMOOTH_MODE == 'range', f'production 預設 pct_mode={score.PCT_MODE!r}、smooth_mode={sel.SMOOTH_MODE!r}')
    N = score.score_table(M, REF); check(N.equals(score.score_table(M, REF, pct_mode='period')) and not N.equals(score.score_table(M, REF, pct_mode='pooled')), 'score_table 預設＝pct_mode=period（≠ pooled）')
    check(sel.select(df, N) == sel.select(df, N, smooth_mode='range') and sel.suitability(N) == sel.suitability(N, 'range') and sd.range_bests(N) == sd.range_bests(N, 'range'), 'select／suitability／range_bests 預設＝smooth_mode=range')
    check(sd.ref_stock_bests(REF).equals(sd.ref_stock_bests(REF, pct_mode='period', smooth_mode='range')), 'ref_stock_bests 預設＝period＋range')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_') and callable(v): print('#', k); v()
    print('ALL PASS')
