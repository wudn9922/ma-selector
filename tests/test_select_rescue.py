"""STRUCTURAL_RESCUE_10PT_10PP（production，只用於短期）的單元測試。
用合成股價跑真正的 core.select.select()；只把「平滑結構分」與「反手報酬」換成指定值（monkeypatch smoothed_scores／sar_stats），以精確控制 C1／C2／C3 邊界。
另外與改動前的 core/select.py（git PREV_COMMIT）逐位元組比較：LEGACY、min_period、中期／長期、以及不觸發 rescue 的短期都必須完全相同。
用法：python tests/test_select_rescue.py"""
import subprocess, sys, types
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, score, metrics, select as sel
PREV_COMMIT = '85b77549d2d785a649fb6f492a4a094b523595a6'          # 改動前（規則 B、尚無 rescue）
DF = data.normalize(synth(7))
PERIODS = np.arange(15, 111)

def prev_module():
    src = subprocess.run(['git', 'show', f'{PREV_COMMIT}:core/select.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType('core._select_prev'); m.__package__ = 'core'; exec(compile(src, 'core/select.py@prev', 'exec'), m.__dict__); return m
PREV = prev_module()

def run(scores, sars, mod=sel, **kw):
    """scores／sars：{period: 值}。沒列出的週期結構分＝0（不會成為候選）、反手報酬＝0。回傳 select() 結果。"""
    sm = np.array([float(scores.get(int(p), 0.)) for p in PERIODS])
    def fake_smoothed(S): return PERIODS.copy(), sm.copy()
    def fake_sar(O, H, L, C, atr, ma, lo):
        p = int(np.isnan(ma).sum()) + 1; return dict(報酬=float(sars.get(p, 0.)), 回撤=-0.1, 勝率=0.5, 筆數=10)
    o1, o2 = mod.smoothed_scores, mod.sar_stats; mod.smoothed_scores, mod.sar_stats = fake_smoothed, fake_sar
    try: return mod.select(DF, None, **kw)
    finally: mod.smoothed_scores, mod.sar_stats = o1, o2

def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

def short_case(s_cur, s_sb, r_cur, r_sb, cur=20, sb=25):
    """短期只有兩個候選：cur（規則 B final）與 sb（結構分第一）。中期、長期放一組形狀相同的候選。"""
    sc = {cur: s_cur, sb: s_sb, 36: s_cur, 40: s_sb, 60: s_cur, 80: s_sb}; sr = {cur: r_cur, sb: r_sb, 36: r_cur, 40: r_sb, 60: r_cur, 80: r_sb}
    return run(sc, sr)

def test_rescue_true():
    R = short_case(50., 65., .50, .42)                         # C1：差 8pp 被 5pp gate 排除；C2：+15；C3：差 8pp ≤ 10pp
    check(R['短期']['final'] == 25, f"rescue 成立 → 結構分第一 SMA25（得 {R['短期']['final']}）")
    check(R['中期']['final'] == 36 and R['長期']['final'] == 60, f"中期／長期同樣形狀也不 rescue（{R['中期']['final']}／{R['長期']['final']}）")

def test_c2_boundary():
    check(short_case(50., 60., .50, .42)['短期']['final'] == 25, 'C2 差正好 10.0 → rescue')
    check(short_case(50., 59.999999999, .50, .42)['短期']['final'] == 20, 'C2 差 9.999999999 → 不 rescue')
    check(short_case(50., float(np.nextafter(60., 0.)), .50, .42)['短期']['final'] == 20, 'C2 差比 10.0 少一個 ulp → 不 rescue')

def test_c3_boundary():
    best = .75; edge = best - sel.RESCUE_SAR_PP
    check(short_case(50., 65., best, edge)['短期']['final'] == 25, f'C3 SAR 正好 best−0.10（{edge!r}）→ rescue')
    check(short_case(50., 65., best, float(np.nextafter(edge, -1.)))['短期']['final'] == 20, 'C3 SAR 比 best−0.10 低一個 ulp → 不 rescue')
    check(short_case(50., 65., best, best - .1001)['短期']['final'] == 20, 'C3 差 10.01pp → 不 rescue')

def test_c1_false():
    R = short_case(50., 65., .50, .46)                         # SB 差 4pp，本來就在 finalists → 規則 B 直接選 SB
    check(R['短期']['final'] == 25, '結構分第一本來就在 5pp finalists → 規則 B 選它（不是 rescue override）')
    R = run({20: 50., 25: 65., 30: 64.}, {20: .50, 25: .40, 30: .47})   # SB=25 被排除；finalists={20,30}；規則 B → 30（64）；C2：65 < 64+10 → 不 rescue
    check(R['短期']['final'] == 30, f"C1 成立但 C2 不成立 → 維持規則 B final SMA30（得 {R['短期']['final']}）")
    R = run({20: 60., 25: 55.}, {20: .50, 25: .30})            # 結構分第一就是規則 B final → C1 false
    check(R['短期']['final'] == 20, '結構分第一＝規則 B final → 不變')

def test_structural_tie_shorter():
    R = run({22: 70., 30: 70., 26: 55.}, {22: .54, 30: .54, 26: .60})   # 22、30 同分第一且都被 gate 排除；C2 70 ≥ 65、C3 .54 ≥ .50
    check(R['短期']['final'] == 22, f"結構分完全同分 → 取較短 SMA22（得 {R['短期']['final']}）")
    R = run({22: 70., 30: 70., 26: 55.}, {22: .54, 30: .58, 26: .60})   # 30 在 finalists、22 不在；SB 仍是較短的 22 → C1 成立；規則 B final＝30（70）→ C2 70 < 80 不成立
    check(R['短期']['final'] == 30, f"同分時 SB 取較短；SB 對規則 B final 沒有 +10 → 不 rescue（得 {R['短期']['final']}）")

def test_scope_mid_long():
    for lo, hi, nm in ((36, 40, '中期'), (60, 80, '長期')):
        R = run({lo: 50., hi: 65., 20: 50.}, {lo: .50, hi: .42, 20: .5})
        check(R[nm]['final'] == lo, f'{nm} 符合 C1／C2／C3 的形狀也不 rescue（維持規則 B SMA{lo}）')

def test_rounded_vs_unrounded():
    R = short_case(50.04, 60.04, .50, .42)                    # 顯示分數 50.0／60.0，但未四捨五入差 10.0 → rescue
    check(R['短期']['final'] == 25, '用未四捨五入結構分判斷 C2')
    R = short_case(50.06, 60.04, .50, .42)                    # 顯示 50.1／60.0、真實差 9.98 → 不 rescue
    check(R['短期']['final'] == 20, '未四捨五入差 9.98 → 不 rescue（不看顯示值）')

def test_legacy_and_other_paths_unchanged():
    cases = [({20: 50., 25: 65., 36: 50., 40: 65., 60: 50., 80: 65.}, {20: .50, 25: .42, 36: .50, 40: .42, 60: .50, 80: .42}),
             ({22: 70., 30: 70., 26: 55.}, {22: .54, 30: .54, 26: .60}), ({17: 40., 29: 38., 33: 35.}, {17: .1, 29: .3, 33: -.2})]
    for sc, sr in cases:
        for kw in (sel.LEGACY, dict(final_rule='min_period'), dict(method='bt'), dict(gap=5, final_rule='min_period')):
            check(run(sc, sr, **kw) == run(sc, sr, PREV, **kw), f'{kw}：與改動前 select 完全相同')
        a, b = run(sc, sr), run(sc, sr, PREV)
        check(a['中期'] == b['中期'] and a['長期'] == b['長期'] and a['短期']['cands'] == b['短期']['cands'], 'production：中期／長期整組與短期候選與改動前完全相同（只有短期 final 可能被 rescue）')
    assert sel.LEGACY == dict(gap=15, method='bt', longonly=True) and sel.GAP == 15 and sel.RESCUE_POINTS == 10.0 and sel.RESCUE_SAR_PP == 0.10

def test_real_pipeline_vs_prev():
    """不 patch：合成股價＋repo 的 reference.parquet，真正跑 metrics／score／select；LEGACY 與 min_period 逐位元組相同；production 只有短期 final 可能不同，且不同時必須符合 C1／C2／C3。"""
    ref = pd.read_parquet(ROOT / 'data' / 'reference.parquet'); n_diff = 0
    for seed in (3, 11, 29, 41, 57, 88):
        df = data.normalize(synth(seed)); S = score.score_table(metrics.compute_metrics(df), ref)
        for kw in (sel.LEGACY, dict(final_rule='min_period')): assert sel.select(df, S, **kw) == PREV.select(df, S, **kw)
        a, b = sel.select(df, S), PREV.select(df, S)
        assert a['中期'] == b['中期'] and a['長期'] == b['長期'] and a['短期']['cands'] == b['短期']['cands']
        if a['短期']['final'] != b['短期']['final']:
            n_diff += 1; c = a['短期']['cands']; best = max(x['反手報酬'] for x in c); sb = min(c, key=lambda x: (-x['結構分'], x['均線'])); f = next(x for x in c if x['均線'] == b['短期']['final'])
            assert a['短期']['final'] == sb['均線'] and sb['反手報酬'] < best - 0.05 and sb['結構分'] >= f['結構分'] + 10 and sb['反手報酬'] >= best - 0.10
    check(True, f'真實流程（6 檔合成股價）：LEGACY／min_period 逐位元組相同；production 只在 rescue 條件成立時改短期 final（本次 {n_diff} 檔）')

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print('#', n); f()
    print('ALL PASS')
