"""突破幅度實驗（experiments/selector_v2/MAGNITUDE_SPEC.md）的測試（合成資料）
1) metrics：既有欄位對改動前（BASE）逐位元組相同；新增 6 欄 mfe_* 在最後且等於手算（含空單、最後一筆未平倉）；沒有突破 → n=0、med=NaN → 特徵 0
2) score_mag：w_mag=0 時 score_table_mag／score_table_v2_mag 與 score.score_table／score_v2.score_table_v2 完全相同；權重合計 1、幅度權重正確（短期、中期）
3) select_v2：預設輸出與 BASE 版、score_fn=None 明確傳入、score_fn=score_table_v2 相同；score_fn 真的被使用
4) production 檔（select／score／events／score_v2）與 BASE 逐位元組相同；build_reference_mag 的欄位
用法：python tests/test_magnitude.py"""
import subprocess, sys, types
from functools import partial
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, score, score_v2 as sv2, score_mag as sm, metrics, select as sel, select_v2 as sv, events as ev
from core.data import wilder_atr
from core.ma import moving_average
import build_reference_mag as brm
BASE = '7e32361'          # 加入 mfe 欄位／score_mag 之前（等同當時的 HEAD）
def git_show(path): return subprocess.run(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, capture_output=True, check=True).stdout
def old_module(name):
    m = types.ModuleType(f'core._{name}_old'); m.__package__ = 'core'; m.__file__ = str(ROOT / 'core' / f'{name}.py'); exec(compile(git_show(f'core/{name}.py').decode(), f'core/{name}.py@old', 'exec'), m.__dict__); return m
OLD_M, OLD_SV = old_module('metrics'), old_module('select_v2')
SEEDS = (3, 11, 29); POOL = (101, 102, 103, 104, 105, 106); MFE = [f'mfe_{k}@{W}' for W in (252, 504, 756) for k in ('n', 'med')]
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
def stock(seed, n=1300): return data.normalize(synth(seed, n))
_M = {}
def M_of(seed):
    if seed not in _M: _M[seed] = metrics.compute_metrics(stock(seed))
    return _M[seed]
def tobytes(s): return s.to_numpy().tobytes()
_REF = {}
def refs():
    if not _REF:
        _REF['p'] = pd.concat([score.make_features(M_of(s)).assign(ticker=f'S{s}') for s in POOL], ignore_index=True)
        _REF['v2'] = pd.concat([sv2.make_features_v2(M_of(s)).assign(ticker=f'S{s}') for s in POOL], ignore_index=True)
        _REF['m'] = pd.concat([brm.features(M_of(s)).assign(ticker=f'S{s}') for s in POOL], ignore_index=True)
    return _REF['p'], _REF['v2'], _REF['m']
def same_val(a, b): return repr(a) == repr(b)             # 結果含 nan，用 repr 比

def test_metrics_old_columns_identical():
    for seed in SEEDS:
        o = OLD_M.compute_metrics(stock(seed)); n = M_of(seed); oc = list(o.columns)
        check(list(n.columns)[:len(oc)] == oc and n[oc].equals(o) and all(tobytes(n[c]) == tobytes(o[c]) for c in oc), f'seed {seed}：既有 {len(oc)} 欄（含 @756）的值（逐位元組）與順序和 BASE 相同')
        check(list(n.columns)[len(oc):] == MFE, f'seed {seed}：多出來的欄位正好是最後 6 欄 {MFE}')

def hand_mfe(df, p, W):
    """手算：只取 plog 裡 kind=='B' 且 tin ≥ N−W 的持倉；多單 (max(H[tin..tout])−ep)/atr[tin]，空單 (ep−min(L[tin..tout]))/atr[tin]"""
    O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df); N = len(C)
    _b, _w, _r, plog, _t = ev.events(O, H, L, C, moving_average(df.close, p), atr); v = []
    for tin, tout, sg, ep, _xp, kind in plog:
        if kind != 'B' or tin < N - W: continue
        hs = [H[t] for t in range(tin, tout + 1)]; ls = [L[t] for t in range(tin, tout + 1)]
        v.append((max(hs) - ep) / atr[tin] if sg == 1 else (ep - min(ls)) / atr[tin])
    return v, plog, N

def test_mfe_matches_hand():
    seen_short = seen_open = seen_R = False
    for seed in SEEDS:
        df = stock(seed); n = M_of(seed)
        for p in (15, 20, 33, 45, 70, 110):
            r = n[n.period == p].iloc[0]
            for W in (252, 504, 756):
                v, plog, N = hand_mfe(df, p, W); exp_med = float(np.median(v)) if v else np.nan
                check(r[f'mfe_n@{W}'] == len(v) and np.array_equal(np.float64(r[f'mfe_med@{W}']), np.float64(exp_med), equal_nan=True), f'seed {seed} SMA{p} @{W}：mfe_n={len(v)}、mfe_med={exp_med:.4f} 等於手算')
            pl = [x for x in plog if x[5] == 'B' and x[0] >= N - 756]
            seen_short |= any(x[2] == -1 for x in pl); seen_open |= any(x[1] == N - 1 for x in pl); seen_R |= any(x[5] == 'R' for x in plog)
    check(seen_short and seen_open and seen_R, '測試涵蓋：有空單突破持倉、有最後一筆未平倉、plog 裡確實有 R（回測進場）要被排除')
    # 空單、多單的公式各用一個具體持倉直接驗證
    df = stock(3); O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df)
    for p in range(15, 111):
        pl = ev.events(O, H, L, C, moving_average(df.close, p), atr)[3]; sh = [x for x in pl if x[5] == 'B' and x[2] == -1 and x[0] >= len(C) - 252]
        if sh: break
    a, b, _sg, e, _x, _k = sh[0]; exp = (e - L[a:b + 1].min()) / atr[a]
    check(sh and exp >= 0 and any(abs(exp - m) < 1e-12 for m in hand_mfe(df, p, 252)[0]), f'空單持倉（SMA{p}，{a}→{b}）：MFE＝(進場價−持有期間最低)/ATR＝{exp:.3f} ≥ 0 且在 mfe 集合內')

def test_mfe_nan_to_zero():
    n = 400; t = np.arange(n); c = 100 + 0.2 * np.sin(t / 7.); df = data.normalize(pd.DataFrame(dict(time=pd.date_range('2024-01-01', periods=n).strftime('%Y-%m-%d'), open=c, high=c * 1.0005, low=c * 0.9995, close=c, volume=1000)))
    M = metrics.compute_metrics(df, periods=(20, 60)); check((M['mfe_n@252'] == 0).all() and M['mfe_med@252'].isna().all() and (M['mfe_n@756'] == 0).all(), '沒有突破：mfe_n=0、mfe_med=NaN')
    F = sm.make_features_mag(M); check(all((F[c] == 0).all() for c in ('幅度', '幅度_1y', '幅度_2y', '幅度_3y')), 'NaN → 0：幅度、幅度_1y／2y／3y 都是 0')
    M = M_of(3); F = sm.make_features_mag(M); F0 = score.make_features(M)
    check(F[list(F0.columns)].equals(F0) and list(F.columns) == list(F0.columns) + ['幅度_1y', '幅度_2y', '幅度_3y', '幅度'], 'make_features_mag：前面的欄位＝score.make_features，後面多 幅度_1y／2y／3y、幅度')
    check(all(np.array_equal(F[f'幅度_{y}'].to_numpy(), M[f'mfe_med@{W}'].fillna(0).to_numpy()) for y, W in sv2.WINDOWS) and F['幅度'].equals(F['幅度_1y']) and (F['幅度'] >= 0).all(), '幅度_y＝mfe_med@252／504／756 的 NaN→0；幅度＝幅度_1y；非負')

def test_zero_weight_equals_original():
    rp, r2, rm = refs(); chk = []
    for seed in SEEDS:
        M = M_of(seed)
        for ws in (None, {'短': {'突破': 1, '二日': 2, '回測': 3, '雜訊': 4, '穿插': 5}, '長': {'快敗': .3, '穿插': .7}}):
            S0, S1 = score.score_table(M, rp, ws), sm.score_table_mag(M, rm, ws, w_mag=0)
            ok = S1[list(S0.columns)].equals(S0) and all(tobytes(S1[c]) == tobytes(S0[c]) for c in S0.columns) and list(S1.columns) == list(S0.columns) + ['p幅度']
            check(ok, f'seed {seed} ws={"預設" if ws is None else "自訂"}：score_table_mag(w_mag=0) 與 score.score_table 逐位元組相同（精確相等，不用容差）'); chk.append(ok)
            T0 = sv2.score_table_v2(M, r2, ws); T1 = sm.score_table_v2_mag(M, rm, ws, w_mag=0)
            ok = T1[list(T0.columns)].equals(T0) and all(tobytes(T1[c]) == tobytes(T0[c]) for c in T0.columns)
            check(ok, f'seed {seed} ws={"預設" if ws is None else "自訂"}：score_table_v2_mag(w_mag=0) 與 score_table_v2 逐位元組相同')
    S = sm.score_table_mag(M_of(3), rm); S0 = sm.score_table_mag(M_of(3), rm, w_mag=0)
    check(not S['分數_短'].equals(S0['分數_短']) and not sm.score_table_v2_mag(M_of(3), rm)['分數_2y'].equals(sm.score_table_v2_mag(M_of(3), rm, w_mag=0)['分數_2y']), 'w_mag=.2 時分數確實不同（幅度有作用）')

def test_weights():
    for ws in (None, {'短': {'突破': 1, '二日': 2, '回測': 3, '雜訊': 4, '穿插': 5}, '長': {'快敗': .3, '穿插': .7}}):
        for w in (0., .1, .2, .5):
            m = sm.mag_ws(ws, w); n = score.normalize_ws(ws or score.WS)
            check(abs(sum(m['短'].values()) - 1) < 1e-12 and abs(sum(m['長'].values()) - 1) < 1e-12 and m['短']['幅度'] == w and m['長'] == n['長'] and list(m['短'])[:5] == list(n['短']) and all(abs(m['短'][k] - n['短'][k] * (1 - w)) < 1e-15 for k in n['短']), f'mag_ws ws={"預設" if ws is None else "自訂"} w_mag={w}：短期合計 1、幅度＝w_mag、其餘＝使用者權重 ×(1−w_mag)、長期不變')
    m = sm.mag_ws(None, .2); check(all(abs(m['短'][k] - sm.WS_MAG['短'][k]) < 1e-12 for k in sm.WS_MAG['短']) and m['長'] == score.normalize_ws(score.WS)['長'] and sm.WS_MAG['長'] == score.WS['長'] and abs(sum(sm.WS_MAG['短'].values()) - 1) < 1e-12, 'mag_ws(None, .2) ≈ WS_MAG（突破 .20、二日 .16、回測 .12、雜訊 .12、穿插 .20、幅度 .20；長期不變）')
    check(sm.FEATS_MAG == score.FEATS + ['幅度'], 'FEATS_MAG＝FEATS＋幅度')
    rp, r2, rm = refs(); M = M_of(11)
    for w in (.2, .35):
        S = sm.score_table_mag(M, rm, w_mag=w); S0 = sm.score_table_mag(M, rm, w_mag=0); W5 = score.normalize_ws(score.WS)
        pc = lambda k: S['p' + k]
        exp_s = sum(v * (1 - w) * (S['p穿插_1y'] if k == '穿插' else pc(k)) for k, v in W5['短'].items()) + w * pc('幅度')
        mid = {'突破': (W5['短']['突破'] * (1 - w)) / 2, '二日': (W5['短']['二日'] * (1 - w)) / 2, '回測': (W5['短']['回測'] * (1 - w)) / 2, '雜訊': (W5['短']['雜訊'] * (1 - w)) / 2}
        exp_m = sum(v * pc(k) for k, v in mid.items()) + (W5['短']['穿插'] * (1 - w) + .5) / 2 * S['p穿插_2y'] + w / 2 * pc('幅度') + .5 / 2 * S['p快敗_2y']
        exp_l = .5 * S['p穿插_3y'] + .5 * S['p快敗_3y']
        check(np.allclose(S['分數_短'], exp_s, atol=1e-9, rtol=0) and np.allclose(S['分數_中'], exp_m, atol=1e-9, rtol=0) and np.allclose(S['分數_長'], exp_l, atol=1e-9, rtol=0) and S['分數_長'].equals(S0['分數_長']), f'w_mag={w}：短期＝0.8… 手算（幅度 {w}）；中期＝短長平均權重（幅度權重 {w}/2）；長期不含幅度且不變')
        check(np.allclose(S['分數_短'], (1 - w) * S0['分數_短'] + w * S['p幅度'], atol=1e-9, rtol=0), f'w_mag={w}：分數_短 ＝ (1−w)·舊分數_短 ＋ w·p幅度')
        check(np.array_equal(S['分數'].to_numpy(), np.where(S.period <= 33, S['分數_短'], np.where(S.period <= 45, S['分數_中'], S['分數_長']))), '分數 依 15–33 短、34–45 中、46+ 長 組合')
        T = sm.score_table_v2_mag(M, rm, w_mag=w); T0 = sm.score_table_v2_mag(M, rm, w_mag=0)
        check(all(np.allclose(T[f'分數_{y}'], (1 - w) * T0[f'分數_{y}'] + w * T[f'p幅度_{y}'], atol=1e-9, rtol=0) for y in ('1y', '2y', '3y')), f'w_mag={w}：v2 每視窗 分數_y ＝ (1−w)·舊 ＋ w·p幅度_y')
    # 幅度百分位對 ref_mag 手算
    M = M_of(11); F = sm.make_features_mag(M); S = sm.score_table_mag(M, rm); T = sm.score_table_v2_mag(M, rm)
    check(np.array_equal(S['p幅度'].to_numpy(), score.pct_vs(np.sort(rm['幅度'].to_numpy(float)), F['幅度'].to_numpy(float))) and all(np.array_equal(T[f'p幅度_{y}'].to_numpy(), score.pct_vs(np.sort(rm[f'幅度_{y}'].to_numpy(float)), F[f'幅度_{y}'].to_numpy(float))) for y in ('1y', '2y', '3y')), 'p幅度／p幅度_y ＝ 對 ref_mag 的 pct_vs')
    # 實驗版回到 select.select：只吃 period／分數
    df = stock(11); P = sel.select(df, S); check(set(P) == {'短期', '中期', '長期'} and 15 <= P['短期']['final'] <= 33 and 34 <= P['中期']['final'] <= 45 and 46 <= P['長期']['final'], 'sel.select(df, score_table_mag(...)) 可用，三個區間 final 落在範圍內')

def test_select_v2_default_unchanged():
    rp, r2, rm = refs()
    for seed in SEEDS:
        df, M = stock(seed), M_of(seed); L = sel.select(df, score.score_table(M, rp))['長期']
        d = sv.select_v2(df, M, r2, long_result=L); o = OLD_SV.select_v2(df, M, r2, long_result=L)
        check(same_val(d, o), f'seed {seed}：select_v2 預設輸出與 BASE 版相同'); check(same_val(sv.select_v2(df, M, r2, long_result=L, score_fn=None), d), f'seed {seed}：score_fn=None 明確傳入＝預設')
        check(same_val(sv.select_v2(df, M, r2, long_result=L, score_fn=sv2.score_table_v2), d), f'seed {seed}：score_fn=score_table_v2 ＝預設')
        check(same_val(sv.select_v2(df, M, rm, long_result=L, score_fn=partial(sm.score_table_v2_mag, w_mag=0)), d), f'seed {seed}：score_fn=score_table_v2_mag(w_mag=0)＋ref_mag ＝預設（特徵值相同的基準）')
        dm = sv.select_v2(df, M, rm, long_result=L, score_fn=partial(sm.score_table_v2_mag, w_mag=.2))
        check(list(dm) == list(d) and 15 <= dm['短期']['final1'] <= 45 and 46 <= dm['中期']['final'] <= 70 and dm['長期'] is L, f'seed {seed}：w_mag=.2 結構相同、final 在範圍內')
    calls = []; f = lambda M, r, ws=None: (calls.append((r, ws)), sv2.score_table_v2(M, r2, ws))[1]; df, M = stock(3), M_of(3)
    sv.select_v2(df, M, 'REF', ws={'短': {}}, score_fn=f); check(calls == [('REF', {'短': {}})], 'score_fn 被呼叫一次，參數 (M, ref, ws) 原樣傳入')

def test_production_and_reference():
    for f in ('core/select.py', 'core/score.py', 'core/events.py', 'core/score_v2.py'):
        check((ROOT / f).read_bytes() == git_show(f), f'{f} 與 BASE（{BASE}）逐位元組相同')
    rp, r2, rm = refs(); check(len(rm.columns) == len(set(rm.columns)), 'ref_mag 欄名無重複')
    F = brm.features(M_of(3)); c = list(F.columns)
    check(c == ['period'] + sm.FEATS_ALL_MAG and len(c) == len(set(c)) and set(c) >= set(score.FEATS) | set(sv2.FEATS_V2) | set(sm.FEATS_MAG) | set(sm.FEATS_V2_MAG) and len(F) == 96 and F.period.is_unique, 'reference_mag 特徵欄：period＋現行＋v2＋幅度，無重複欄名，一股一週期一列（96 列）')
    check(all(np.array_equal(F[k].to_numpy(), score.make_features(M_of(3))[k].to_numpy()) for k in score.FEATS) and all(np.array_equal(F[k].to_numpy(), sv2.make_features_v2(M_of(3))[k].to_numpy()) for k in sv2.FEATS_V2), '特徵值與 make_features／make_features_v2 相同')
    src = (ROOT / 'scripts/build_reference_mag.py').read_text(); check("'data/reference_mag.parquet'" in src and "version='mag'" in src, 'build_reference_mag：輸出路徑與 json version=mag')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_') and callable(v): print('#', k); v()
    print('ALL PASS')
