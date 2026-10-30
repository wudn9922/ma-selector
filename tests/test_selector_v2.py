"""實驗選線 v2（experiments/selector_v2/SPEC.md）的測試（合成資料）
1) metrics：既有欄位對改動前（OLD_COMMIT）逐位元組相同（值＋欄位順序）；新增的 @756 欄位存在且等於手算
2) production 不變：score.score_table／select.select 對舊版（OLD_COMMIT）結果完全相同
3) score_v2：1y 特徵與 分數_1y 等於現行 production（同一個合成基準池）
4) select_v2：合成股票的不變量；monkeypatch 平滑分數與 sar_stats 精確控制 final2 的三種來源（候選內／放寬／找不到）、規則 B、短期 rescue、中期無 rescue
用法：python tests/test_selector_v2.py"""
import subprocess, sys, types
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, score, score_v2 as sv2, metrics, select as sel, select_v2 as sv, events as ev
from core.data import wilder_atr
from core.ma import moving_average
OLD_COMMIT = '474d8f6'          # 加入 @756／v2 之前
def old_module(name):
    src = subprocess.run(['git', 'show', f'{OLD_COMMIT}:core/{name}.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType(f'core._{name}_old'); m.__package__ = 'core'; m.__file__ = str(ROOT / 'core' / f'{name}.py'); exec(compile(src, f'core/{name}.py@old', 'exec'), m.__dict__); return m
OLD_M, OLD_SC, OLD_S = old_module('metrics'), old_module('score'), old_module('select')
REF = pd.read_parquet(ROOT / 'data/reference.parquet'); SEEDS = (3, 11, 29); POOL = (101, 102, 103, 104, 105, 106); NEW756 = [f'{k}@756' for k in ('A_raw_n', 'A_raw', 'A_d2_n', 'A_d2', 'A_rt_n', 'A_rt', 'A_wick')]; NEWMFE = [f'mfe_{k}@{W}' for W in (252, 504, 756) for k in ('n', 'med')]   # 後面追加的突破幅度 6 欄
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
def stock(seed, n=1300): return data.normalize(synth(seed, n))
_M = {}
def M_of(seed):
    if seed not in _M: _M[seed] = metrics.compute_metrics(stock(seed))
    return _M[seed]
def old_M_of(seed): return M_of(seed)[list(OLD_M.compute_metrics(stock(seed)).columns)]
def tobytes(s): return s.to_numpy().tobytes()
_REF2 = {}
def ref_v2():
    if 'r' not in _REF2:
        _REF2['r'] = pd.concat([sv2.make_features_v2(M_of(s)).assign(ticker=f'S{s}') for s in POOL], ignore_index=True)
        _REF2['p'] = pd.concat([score.make_features(M_of(s)).assign(ticker=f'S{s}') for s in POOL], ignore_index=True)
    return _REF2['r'], _REF2['p']

def test_metrics_old_columns_identical():
    for seed in SEEDS:
        o = OLD_M.compute_metrics(stock(seed)); n = M_of(seed); oc = list(o.columns)
        check(list(n.columns)[:len(oc)] == oc and n[oc].equals(o) and all(tobytes(n[c]) == tobytes(o[c]) for c in oc), f'seed {seed}：既有 {len(oc)} 欄的值（逐位元組）與順序和舊版相同')
        check(list(n.columns)[len(oc):] == NEW756 + NEWMFE, f'seed {seed}：多出來的欄位正好是 @756 的 7 欄 {NEW756} ＋其後 6 欄 mfe')

def test_756_matches_hand():
    df = stock(3); n = M_of(3); O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df); N = len(C)
    for p in (20, 45, 90):
        brk, wick, rts, _pl, _tr = ev.events(O, H, L, C, moving_average(df.close, p), atr); lo = N - 756
        b = [v['res'] for v in brk if v['t'] >= lo and v['res'] >= 0]; h = [v['res'] for v in brk if v['t'] >= lo and v['res'] >= 0 and v['d2']]
        q = [v['res'] for v in rts if v['t'] >= lo and v['state'] in ('進場', '失敗') and v['res'] >= 0]; w = sum(1 for v in wick if v['t'] >= lo)
        r = n[n.period == p].iloc[0]; fl = lambda x: np.mean(x) if x else np.nan
        exp = {'A_raw_n': len(b), 'A_raw': fl(b), 'A_d2_n': len(h), 'A_d2': fl(h), 'A_rt_n': len(q), 'A_rt': fl(q), 'A_wick': w}
        check(all(np.array_equal(np.float64(r[f'{k}@756']), np.float64(v), equal_nan=True) for k, v in exp.items()), f'SMA{p}：@756 七欄等於手算 {({k: (round(float(v), 4) if v == v else v) for k, v in exp.items()})}')
    r = n[n.period == 20].iloc[0]; check(r['A_raw_n@756'] >= r['A_raw_n@504'] >= r['A_raw_n@252'] and r['A_wick@756'] >= r['A_wick@504'] >= r['A_wick@252'], '視窗單調：@756 ≥ @504 ≥ @252（次數）')

def test_production_unchanged():
    for seed in SEEDS:
        df = stock(seed); Mo = old_M_of(seed); S0 = OLD_SC.score_table(Mo, REF)
        S1 = score.score_table(M_of(seed), REF); S2 = score.score_table(Mo, REF)
        check(S1.equals(S0) and S2.equals(S0) and list(S1.columns) == list(S0.columns), f'seed {seed}：score_table（含 @756 的 M／只含舊欄位的 M）對舊版 DataFrame.equals')
        check(score.make_features(M_of(seed)).equals(OLD_SC.make_features(Mo)), f'seed {seed}：make_features 對舊版相同')
        o = OLD_S.select(df, S0); check(sel.select(df, S1) == o, f'seed {seed}：select.select(df, score_table(M, ref)) 對舊版 ==')
        check(sel.suitability(S1) == OLD_S.suitability(S0), f'seed {seed}：suitability 對舊版相同')

def test_score_v2_matches_production_1y():
    rv, rp = ref_v2(); seed = 11; M = M_of(seed)
    check(all(c in rv.columns for c in sv2.FEATS_V2) and len(sv2.FEATS_V2) == 18 and sv2.FEATS_V2[:4] == ['突破_1y', '二日_1y', '回測_1y', '雜訊_1y'], 'ref_v2 有 FEATS_V2 全部 18 個特徵（突破／二日／回測／雜訊 × 1y/2y/3y ＋ tg／qd × 1y/2y/3y）')
    F, F0 = sv2.make_features_v2(M), score.make_features(M)
    check(all(np.array_equal(F[f'{k}_1y'].to_numpy(), F0[k].to_numpy()) for k in ('突破', '二日', '回測', '雜訊')) and all(F[f'{k}_{y}'].equals(F0[f'{k}_{y}']) for k in ('tg', 'qd') for y in ('1y', '2y', '3y')), '1y 特徵與 make_features 完全相同；tg／qd 相同')
    for ws in (None, {'短': {'突破': 1, '二日': 2, '回測': 3, '雜訊': 4, '穿插': 5}, '長': {'快敗': .5, '穿插': .5}}):
        T, S = sv2.score_table_v2(M, rv, ws), score.score_table(M, rp, ws)
        check(np.array_equal(T['分數_1y'].to_numpy(), S['分數_短'].to_numpy()) and T.period.equals(S.period), f'分數_1y ＝ score_table 的 分數_短（ws={"預設" if ws is None else "自訂"}，同一個基準池）')
    T = sv2.score_table_v2(M, rv); wn = score.normalize_ws(score.WS)['短']; i = 10; R = {c: np.sort(rv[c].to_numpy(float)) for c in sv2.FEATS_V2}; F = sv2.make_features_v2(M)
    for y in ('2y', '3y'):
        pc = lambda c: score.pct_vs(R[c], F[c].to_numpy(float)[i:i + 1])[0]
        exp = sum(wn[k] * pc(f'{k}_{y}') for k in ('突破', '二日', '回測', '雜訊')) + wn['穿插'] * (pc(f'tg_{y}') + pc(f'qd_{y}')) / 2
        check(abs(T[f'分數_{y}'].iloc[i] - exp) < 1e-9 and 0 <= T[f'分數_{y}'].min() and T[f'分數_{y}'].max() <= 100, f'分數_{y} 等於手算（週期 {T.period.iloc[i]}）')
    check({'分數_1y', '分數_2y', '分數_3y'} <= set(T.columns) and all(f'p{k}_{y}' in T.columns for k in ('突破', '二日', '回測', '雜訊', '穿插') for y in ('1y', '2y', '3y')), 'score_table_v2 欄位：三個分數＋各視窗成分百分位')

def test_select_v2_invariants():
    rv, _ = ref_v2(); n_second = {'cands': 0, 'relaxed': 0, None: 0}
    for seed in (3, 11, 29, 41, 57):
        df, M = stock(seed), M_of(seed); S = score.score_table(M, REF); L = sel.select(df, S)['長期']; R = sv.select_v2(df, M, rv, long_result=L); T = sv2.score_table_v2(M, rv)
        check(list(R) == ['短期', '中期', '長期', 'suitability'] and R['長期'] is L, f'seed {seed}：回傳結構，長期原樣帶入（is 同一個物件）')
        check('長期' not in sv.select_v2(df, M, rv), 'long_result 沒給 → 不含 長期')
        s, m = R['短期'], R['中期']; ps = [c['均線'] for c in s['cands']]; pm = [c['均線'] for c in m['cands']]
        check(15 <= s['final1'] <= 45 and s['final1'] in ps, f"短期 final1={s['final1']} 在 15–45 且是候選之一")
        check(m['final'] in pm and 46 <= m['final'] <= 70, f"中期 final={m['final']} 在 46–70 且是候選之一")
        for cs, nm in ((s['cands'], '短期'), (m['cands'], '中期')):
            ps_ = [c['均線'] for c in cs]
            check(1 <= len(cs) <= 5 and all(abs(a - b) > 2 for i, a in enumerate(ps_) for b in ps_[i + 1:]), f'{nm} 候選 {ps_}：1–5 條、兩兩差 >2')
        sm2 = sel.smooth(T.sort_values('period')['分數_2y'].to_numpy()); sm3 = sel.smooth(T.sort_values('period')['分數_3y'].to_numpy())
        check([c['結構分'] for c in s['cands']] == sorted([c['結構分'] for c in s['cands']], reverse=True) and all(c['結構分'] == sm2[c['均線'] - 15] for c in s['cands']), '短期候選依「全序列平滑後」2y 分數由高到低，結構分＝未四捨五入的平滑 2y 分數')
        check(all(c['結構分'] == sm3[c['均線'] - 15] for c in m['cands']) and max(c['結構分'] for c in s['cands']) >= sm2[:31].max() - 1e-12 and all(c['結構分'] >= sm2[:31].max() - 15 for c in s['cands']), '中期用 3y；短期候選與區間最高差 ≤ 15')
        need = {'均線', '分數_2y', '結構分', '分數_1y', '反手報酬', '反手回撤', '反手勝率', '反手筆數', '反手報酬_1y'}
        check(all(set(c) == need for c in s['cands']) and all(set(c) == (need - {'分數_2y', '分數_1y', '反手報酬_1y'}) | {'分數_3y'} for c in m['cands']), '候選欄位齊全（短期含 分數_1y／反手報酬_1y；中期用 分數_3y）')
        # 中期只有規則 B（沒有 rescue）：獨立重算
        best = max(c['反手報酬'] for c in m['cands']); fin = [c for c in m['cands'] if c['反手報酬'] >= best - .05]
        check(m['final'] == min(fin, key=lambda c: (-c['結構分'], c['均線']))['均線'], '中期 final＝規則 B（無 rescue）')
        f1, f2, src = s['final1'], s['final2'], s['second_source']; n_second[src] += 1
        check(src in ('cands', 'relaxed', None) and (f2 is None) == (src is None), f'second_source={src!r} 與 final2={f2} 一致')
        if f2 is not None:
            check(f2 != f1 and 15 <= f2 <= 45 and max(f1, f2) / min(f1, f2) >= 1.5, f'final2={f2} 與 final1={f1} 比例 ≥ 1.5')
            check(f2 in (ps if src == 'cands' else [c['均線'] for c in s['relaxed']]), f'final2 來自 {src}')
        if src == 'cands': check(not s['relaxed'], 'source=cands 時不做放寬')
        if src != 'cands': check(all(max(f1, p) / min(f1, p) < 1.5 for p in ps if p != f1), '沒從候選找到 → 候選內確實沒有比例 ≥1.5 者')
        if src == 'relaxed': check(len(s['relaxed']) <= 5 and all(max(f1, c['均線']) / min(f1, c['均線']) >= 1.5 for c in s['relaxed']), '放寬集合：比例 ≥1.5、最多 5 條')
        check(s['best_2y'] == round(float(sm2[:31].max()), 1) and m['best_3y'] == round(float(sm3[31:56].max()), 1), 'best_2y／best_3y＝區間內平滑最高分')
        su = R['suitability']; check(set(su) == {'short_2y', 'short_1y', 'mid_3y'} and su['short_2y'] == float(sm2[:31].max()) and su['mid_3y'] == float(sm3[31:56].max()) and abs(su['short_1y'] - s['best_1y']) < .05, 'suitability 三個值與 best_* 一致')
        check(sv.select_v2(df, M, rv, gap=3)['短期']['cands'][0] == s['cands'][0] and len(sv.select_v2(df, M, rv, gap=3)['短期']['cands']) <= len(s['cands']), 'gap=3 候選較少且第一名相同')
    print('# final2 來源分佈（5 檔合成）', n_second)

# ---- monkeypatch：精確控制平滑分數與反手報酬 ----
DF = stock(7); PERIODS = np.arange(15, 111)
def run(s2=None, r2=None, s3=None, r3=None, s1=None, r1=None, **kw):
    """s*：{period: 平滑分數}（沒列出＝0，不會成為候選）；r*：{period: 反手報酬}（沒列出＝0）；r1＝252 視窗的反手報酬。回傳 (結果, 呼叫過的 (週期, 視窗) 集合)"""
    sc = {'1y': s1 or s2 or {}, '2y': s2 or {}, '3y': s3 or {20: 50., 50: 50.}}; calls = set(); N = len(DF)
    def fake_smoothed(T, y): return PERIODS.copy(), np.array([float(sc[y].get(int(p), 0.)) for p in PERIODS])
    def fake_sar(O, H, L, C, atr, ma, lo):
        p = int(np.isnan(ma).sum()) + 1; W = N - lo; calls.add((p, W)); d = {252: r1 if r1 is not None else r2, 504: r2, 756: r3}[W]
        return dict(報酬=float((d or {}).get(p, 0.)), 回撤=-0.1, 勝率=0.5, 筆數=10)
    o = (sv.smoothed_v2, sv.score_table_v2, sel.sar_stats); sv.smoothed_v2, sv.score_table_v2, sel.sar_stats = fake_smoothed, (lambda M, r, ws=None: None), fake_sar
    try: return sv.select_v2(DF, None, None, **kw), calls
    finally: sv.smoothed_v2, sv.score_table_v2, sel.sar_stats = o

def test_second_in_cands():
    R, calls = run({20: 60., 24: 59., 33: 58., 40: 57.}, {20: .50, 24: .50, 33: .48, 40: .45}); s = R['短期']
    check([c['均線'] for c in s['cands']] == [20, 24, 33, 40] and s['final1'] == 20, f"final1＝規則 B 結構分最高 SMA20（得 {s['final1']}）")
    check(s['final2'] == 33 and s['second_source'] == 'cands' and s['relaxed'] == [], f"(a) 24 比例 1.2 不符；33（1.65）、40（2.0）符合 → 規則 B 取結構分高的 33（得 {s['final2']}，來源 {s['second_source']}）")
    check({w for _p, w in calls if _p in (20, 24, 33, 40)} == {504, 252} and {w for _p, w in calls if _p in (20, 50)} >= {756}, 'SAR 視窗：短期候選 504＋252（參考）、中期 756')
    R, _ = run({20: 60., 24: 59., 33: 58., 40: 57.}, {20: .50, 24: .50, 33: .30, 40: .45})
    check(R['短期']['final2'] == 40 and R['短期']['second_source'] == 'cands', f"(a2) 剩餘候選內套規則 B：33 反手報酬落後 >5pp 被排除 → 40（得 {R['短期']['final2']}）")
    R, _ = run({20: 60., 30: 58., 29: 57.}, {20: .5, 30: .5, 29: .5}); check(R['短期']['final2'] == 30, f"(a3) 比例剛好 1.5（20 vs 30）符合；29（1.45）已被間距擋掉（得 {R['短期']['final2']}）")
    R, _ = run({20: 60., 29: 58.}, {20: .5, 29: .5}); check(R['短期']['final2'] is None, '(a4) 20 vs 29 比例 1.45 → 不符')
    R, _ = run({20: 50., 25: 65., 40: 55.}, {20: .50, 25: .42, 40: .45}); s = R['短期']
    check(s['final1'] == 25 and s['final2'] == 40 and s['second_source'] == 'cands', f"(a5) final1 用規則 B＋短期 rescue（25）；final2 比例相對 final1（25→40 為 1.6）（得 {s['final1']}／{s['final2']}）")

def test_second_relaxed():
    base = {36: 60., 33: 59., 30: 58., 27: 57., 43: 56., 20: 55., 22: 54., 17: 52.}; rs = {36: .5, 33: .5, 30: .5, 27: .5, 43: .5, 20: .40, 22: .40, 17: .45}
    R, _ = run(base, rs); s = R['短期']
    check([c['均線'] for c in s['cands']] == [36, 33, 30, 27, 43] and s['final1'] == 36, f"候選被 5 條上限截斷 {[c['均線'] for c in s['cands']]}，final1=36")
    check([c['均線'] for c in s['relaxed']] == [20, 17] and s['final2'] == 20 and s['second_source'] == 'relaxed', f"(b) 候選內 36 無比例 ≥1.5 者 → 放寬：20 通過、22 離 20 只差 2 被間距擋掉、17 通過 → 規則 B 取結構分高的 20（得 {[c['均線'] for c in s['relaxed']]}／{s['final2']}／{s['second_source']}）")
    check(all('反手報酬_1y' in c and '分數_1y' in c for c in s['relaxed']), '放寬候選同樣有 1y 參考欄位')
    rs[20] = .30; R, _ = run(base, rs); check(R['短期']['final2'] == 17 and R['短期']['second_source'] == 'relaxed', f"(b2) 放寬集合內也套規則 B：20 反手報酬落後 15pp 被排除 → 17（得 {R['短期']['final2']}）")

def test_second_none():
    R, _ = run({20: 60., 24: 59., 28: 58., 15: 30.}, {20: .5, 24: .5, 28: .5}); s = R['短期']
    check(s['final2'] is None and s['second_source'] is None and s['relaxed'] == [] and s['final1'] == 20, f"(c) 候選 [20,24,28] 與放寬集合都沒有比例 ≥1.5（15 的分數低於門檻）→ final2＝None（得 {s['final2']}）")
    check(s['cands'] and s['best_2y'] == 60.0, 'final2＝None 時其他欄位仍完整')
    R, _ = run({36: 60., 33: 59., 30: 58., 27: 57., 43: 56., 20: 44.9}, {36: .5, 33: .5, 30: .5, 27: .5, 43: .5, 20: .5})
    check(R['短期']['final2'] is None, '(c2) 放寬時分數門檻＝最高 −15：44.9 < 45 → 不入選 → None')
    R, _ = run({36: 60., 33: 59., 30: 58., 27: 57., 43: 56., 20: 45.}, {36: .5, 33: .5, 30: .5, 27: .5, 43: .5, 20: .5})
    check(R['短期']['final2'] == 20 and R['短期']['second_source'] == 'relaxed', '(c3) 正好 −15（45.0）→ 入選')

def test_rescue_scope_and_mid():
    R, _ = run({20: 50., 25: 65.}, {20: .50, 25: .42}); check(R['短期']['final1'] == 25, 'final1 套用短期 rescue（SB 被 5pp gate 排除、+15 分、差 8pp）')
    R, _ = run({20: 50., 25: 65.}, {20: .50, 25: .42}, s3={50: 50., 55: 65.}, r3={50: .50, 55: .42}); m = R['中期']
    check(m['final'] == 50 and [c['均線'] for c in m['cands']] == [55, 50], f"中期同樣形狀不 rescue，維持規則 B 的 50（得 {m['final']}）；候選依 3y 分數排序 {[c['均線'] for c in m['cands']]}")
    check(set(R['中期']) == {'final', 'cands', 'best_3y'} and R['中期']['best_3y'] == 65.0, '中期欄位：final／cands／best_3y')
    s1 = {20: 40., 25: 70.}; R, _ = run({20: 60., 24: 59.}, {20: .5, 24: .5}, s1=s1); s = R['短期']
    check(s['best_1y'] == 70.0 and s['best_2y'] == 60.0 and R['suitability'] == dict(short_2y=60.0, short_1y=70.0, mid_3y=50.0) and s['final1'] == 20, '1y 只作參考（best_1y／分數_1y），不影響 final1；suitability 三值')
    R, _ = run({20: 60., 24: 59.}, {20: .5, 24: .5}, s1={20: 41.26, 24: 30.}, r1={20: .123}); c = R['短期']['cands'][0]
    check(c['分數_1y'] == 41.3 and c['分數_2y'] == 60.0 and c['結構分'] == 60.0 and c['反手報酬_1y'] == .123 and c['反手報酬'] == .5, '候選：分數_1y 四捨五入到 0.1、結構分未四捨五入、反手報酬＝2y 視窗、反手報酬_1y＝1y 視窗')

def test_build_reference_v2_script():
    old = subprocess.run(['git', 'show', '474d8f6:scripts/build_reference.py'], cwd=ROOT, capture_output=True, text=True).stdout
    check(old and (ROOT / 'scripts/build_reference.py').read_text() == old, '現行 scripts/build_reference.py 與 474d8f6 完全相同（v2 用獨立腳本）')
    src = (ROOT / 'scripts/build_reference_v2.py').read_text()
    check("'data/reference_v2.parquet'" in src and "version='v2'" in src and 'make_features_v2' in src and 'kind' not in src.split('import', 1)[1].replace('compute_metrics(df)', ''), 'build_reference_v2：輸出路徑、json version、make_features_v2、只用 SMA')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_') and callable(v): print('#', k); v()
    print('ALL PASS')
