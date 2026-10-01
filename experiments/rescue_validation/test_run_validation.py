"""run_validation／rescue_rule 的測試（只用合成資料與假 fetcher；不連網、不取得任何真實價格）。用法：python experiments/rescue_validation/test_run_validation.py"""
import copy, hashlib, json, re, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'research'), str(ROOT / 'experiments' / 'sar_confidence')]
import rescue_rule as RR, run_validation as V
import regression_synth as rs
from core import data
MANIFEST = json.loads((HERE / 'freeze_manifest.json').read_text(encoding='utf-8'))
C = lambda p, s, r: dict(period=p, s=s, r=r, n=10)

# ───────── rescue rule ─────────
def test_c1_true_false():
    cs = [C(20, 50., .50), C(25, 65., .42)]                                   # SB=25 被 5pp gate 排除（差 8pp）、+15 分、差 8pp ≤10pp
    r = RR.evaluate(cs); assert r['C1'] and r['C2'] and r['C3'] and r['trigger'] and r['rescue_final'] == 25 and r['current_final'] == 20
    cs = [C(20, 50., .50), C(25, 65., .48)]                                   # SB 在 finalists 內（差 2pp）→ C1 false → 不 trigger（CURRENT 本來就會選 SB）
    r = RR.evaluate(cs); assert not r['C1'] and not r['trigger'] and r['rescue_final'] == r['current_final'] == 25
    cs = [C(20, 50., .50), C(25, 45., .40), C(30, 47., .49)]                  # SB 就是 CURRENT final（20 分別為 50，SB=20）→ C1 false
    r = RR.evaluate(cs); assert r['structural_best_period'] == 20 and not r['C1'] and r['rescue_final'] == r['current_final']

def test_c2_boundary():
    cs = lambda sb: [C(20, 50., .50), C(25, sb, .42)]
    assert RR.evaluate(cs(60.))['trigger']                                    # 剛好 +10.0 → 成立（>=）
    assert RR.evaluate(cs(60.))['C2'] and not RR.evaluate(cs(59.999999))['C2'] and not RR.evaluate(cs(59.999999))['trigger']

def test_c3_boundary():
    best = 0.75; edge = best - RR.SAR_PP                                       # 剛好差 10pp（同一個算式）
    cs = lambda r: [C(20, 50., best), C(25, 65., r)]
    assert RR.evaluate(cs(edge))['C3'] and RR.evaluate(cs(edge))['trigger']
    assert not RR.evaluate(cs(edge - 1e-9))['C3'] and not RR.evaluate(cs(edge - 1e-9))['trigger']
    assert RR.SAR_PP == 0.10 and RR.STRUCT_POINTS == 10.0 and RR.GATE_PP == 0.05

def test_structural_tie_shorter():
    cs = [C(30, 55.5, .30), C(22, 55.5, .30), C(26, 55.5, .30)]
    r = RR.evaluate(cs); assert r['structural_best_period'] == 22 and r['current_final'] == 22 and not r['trigger']
    cs = [C(30, 70., .30), C(22, 70., .30), C(26, 55., .60)]                   # 兩個結構分並列第一 → SB 取較短 22；22、30 都被 gate 排除
    r = RR.evaluate(cs); assert r['structural_best_period'] == 22 and r['current_final'] == 26 and r['C1'] and r['C2'] and not r['C3']

def test_dev_crosscheck_83():
    cc = V.dev_crosscheck(ROOT); assert cc['n'] == 83 and cc['identical'] == 83 and cc['changed_finals'] == [] and cc['ok']

# ───────── 流程（合成資料；假 fetcher） ─────────
def synth_df(seed, n): return rs.synth(seed, n)
def mk_manifest(tmp, primary, fallback, mutate=None):
    m = copy.deepcopy(MANIFEST); m['VALIDATION_TICKERS'] = [dict(rank=31 + i, ticker=t, sha256='x') for i, t in enumerate(primary)]; m['FALLBACK_ORDER'] = [dict(rank=131 + i, ticker=t, sha256='x') for i, t in enumerate(fallback)]
    if mutate: mutate(m)
    p = Path(tmp) / 'm.json'; p.write_text(json.dumps(m), encoding='utf-8'); return p
class Fx:
    def __init__(self, dfs, fail=()): self.dfs = dfs; self.calls = []; self.fail = set(fail)
    def __call__(self, tk):
        self.calls.append(tk)
        if tk in self.fail: raise V.FetchError(f'{tk}: simulated')
        return self.dfs[tk]
ALLOWED = [r'PRODUCTION INTEGRITY：OK.*', r'RESCUE CROSS-CHECK：\d+/\d+ 相同；開發集 finals changed = \d+', r'DATA \S+: bars=\d+ first=\S+ last=\S+ sufficient=(True|False)', r'PRODUCTION RUN \S+: done', r'ALL \d+ RAW OUTPUTS WRITTEN.*']
def dfs():
    return {'P1': synth_df(1, 1000), 'P2': synth_df(2, 500), 'P3': synth_df(3, 1000), 'F1': synth_df(4, 600), 'F2': synth_df(5, 1000), 'F3': synth_df(6, 1000)}

def test_fallback_sequence_and_outputs():
    tmp = Path(tempfile.mkdtemp()); m = mk_manifest(tmp, ['P1', 'P2', 'P3'], ['F1', 'F2', 'F3']); fx = Fx(dfs()); logs = []; out = tmp / 'out1'
    code, st = V.run('2026-09-29', out, m, ROOT, fx, real=False, log=logs.append, n_target=3)
    assert (code, st) == (0, 'RAW_OUTPUTS_WRITTEN_PENDING_COMMIT'), (code, st, logs)
    assert fx.calls == ['P1', 'P2', 'F1', 'F2', 'P3']                          # P2 不足 → F1（也不足）→ 繼續 F2；F3 不動用
    rec = json.loads((out / 'execution_record.json').read_text(encoding='utf-8'))
    assert rec['actual_tickers'] == ['P1', 'F2', 'P3'] and rec['mapping_primary_to_actual'] == {'P1': 'P1', 'P2': 'F2', 'P3': 'P3'} and rec['replacements'][0]['chain'][0]['ticker'] == 'F1' and rec['replacements'][0]['final_replacement'] == 'F2'
    assert all(rec['pre_commit_checks'].values()) and rec['PRICE_DATA_ACCESSED'] is True
    for l in logs: assert any(re.fullmatch(p, l) for p in ALLOWED), f'log 不得洩漏結果：{l}'                   # commit A 之前只印 ticker／bars／dates／status
    r2 = json.loads((out / 'raw_outputs' / 'F2' / 'rescue.json').read_text(encoding='utf-8'))
    for k in ('requested_primary_ticker', 'actual_ticker', 'primary_rank', 'replacement_rank', 'bar_count', 'first_date', 'last_date', 'asof', 'short_candidates', 'current_finalists', 'current_final', 'structural_best_period', 'structural_best_score',
              'observed_best_sar', 'structural_score_advantage', 'sar_gap', 'C1', 'C2', 'C3', 'trigger', 'rescue_final'): assert k in r2, k
    assert r2['requested_primary_ticker'] == 'P2' and r2['primary_rank'] == 32 and r2['replacement_rank'] == 132
    assert set(r2['short_candidates'][0]) == {'period', 'structural_score_unrounded', 'score_displayed_rounded', 'sar_return', 'sar_trades'}
    # production 輸出原樣：selection.json 的短期 final 等於 rescue.json 的 CURRENT final
    sel = json.loads((out / 'raw_outputs' / 'P1' / 'selection.json').read_text(encoding='utf-8')); assert sel['selection']['短期']['final'] == json.loads((out / 'raw_outputs' / 'P1' / 'rescue.json').read_text())['current_final']
    # 一次性守門：同一目錄再跑 → ALREADY_OPENED（不再抓資料）
    fx2 = Fx(dfs()); assert V.run('2026-09-29', out, m, ROOT, fx2, real=True, log=lambda s: None, n_target=3) == (0, 'ALREADY_OPENED') and fx2.calls == []
    # 決定性重跑：新目錄、同樣資料 → raw output index 完全相同
    out2 = tmp / 'out2'; c2, s2 = V.run('2026-09-29', out2, m, ROOT, Fx(dfs()), real=False, log=lambda s: None, n_target=3); assert (c2, s2) == (0, 'RAW_OUTPUTS_WRITTEN_PENDING_COMMIT')
    assert (out / 'raw_outputs' / 'index.json').read_bytes() == (out2 / 'raw_outputs' / 'index.json').read_bytes()
    # finalize（無 trigger 或有 trigger 都不判 PASS/FAIL）
    summ = V.finalize(out, 'a' * 40, check_git=False, log=lambda s: None)
    assert summ['trigger_count'] == len(summ['trigger_tickers']) and summ['VALIDATION_STATUS'] == ('INSUFFICIENT_VALIDATION' if summ['trigger_count'] == 0 else 'MANUAL_REVIEW_REQUIRED')
    assert json.loads((out / 'execution_record.json').read_text())['status'] == 'RAW_OUTPUTS_COMMITTED_BEFORE_EXPOSURE'

def test_fetch_failure_blocks_no_fallback():
    tmp = Path(tempfile.mkdtemp()); m = mk_manifest(tmp, ['P1', 'P2', 'P3'], ['F1', 'F2', 'F3']); fx = Fx(dfs(), fail=['P2']); out = tmp / 'o'
    code, st = V.run('2026-09-29', out, m, ROOT, fx, real=False, log=lambda s: None, n_target=3)
    assert st == 'BLOCKED_FETCH_ERROR' and code != 0 and fx.calls == ['P1', 'P2'] and not (out / 'raw_outputs').exists() and not (out / 'execution_record.json').exists()   # 不替補、不繼續
    b = json.loads((out / 'execution_blocked.json').read_text(encoding='utf-8')); assert 'P2' in b['details']['message'] and b['RESULTS_GENERATED'] is False and b['PRICE_DATA_ACCESSED'] is True
    assert V.run('2026-09-29', out, m, ROOT, Fx(dfs()), real=False, log=lambda s: None, n_target=3)[1] != 'ALREADY_OPENED'                  # blocked 不算已開封

def test_empty_data_is_fetch_error():
    tmp = Path(tempfile.mkdtemp()); d = dfs(); d['P2'] = d['P2'].iloc[0:0]; m = mk_manifest(tmp, ['P1', 'P2', 'P3'], ['F1', 'F2', 'F3'])
    assert V.run('2026-09-29', tmp / 'o', m, ROOT, Fx(d), real=False, log=lambda s: None, n_target=3)[1] == 'BLOCKED_FETCH_ERROR'

def test_fallback_pool_exhausted():
    tmp = Path(tempfile.mkdtemp()); d = dfs(); m = mk_manifest(tmp, ['P1', 'P2', 'P3'], ['F1'])
    code, st = V.run('2026-09-29', tmp / 'o', m, ROOT, Fx(d), real=False, log=lambda s: None, n_target=3); assert st == 'BLOCKED_INSUFFICIENT_FALLBACK_POOL' and not (tmp / 'o' / 'raw_outputs').exists()

def test_integrity_drift_before_fetch():
    for mutate in (lambda m: m['reference'].__setitem__('sha256', '0' * 64), lambda m: m['production']['file_sha256_at_production_commit'].__setitem__('core/select.py', '0' * 64),
                   lambda m: m['production']['file_sha256_at_production_commit'].__setitem__('core/events.py', '0' * 64), lambda m: m['production'].__setitem__('tree', '0' * 40), lambda m: m.__setitem__('asof', '2026-09-28')):
        tmp = Path(tempfile.mkdtemp()); m = mk_manifest(tmp, ['P1', 'P2', 'P3'], ['F1'], mutate); fx = Fx(dfs()); out = tmp / 'o'
        code, st = V.run('2026-09-29', out, m, ROOT, fx, real=False, log=lambda s: None, n_target=3)
        assert st == 'BLOCKED_INTEGRITY_DRIFT' and fx.calls == [], (st, fx.calls)                                               # 在任何價格存取之前停止
        assert json.loads((out / 'execution_blocked.json').read_text())['PRICE_DATA_ACCESSED'] is False
    bad = V.integrity_gate({**MANIFEST, 'VALIDATION_TICKERS': MANIFEST['VALIDATION_TICKERS'][::-1]}, ROOT, check_ranking=True); assert not bad[0] and 'rank 31–130 ordered list' in bad[1]    # 排名順序不同也算 drift
    ok = V.integrity_gate(MANIFEST, ROOT, check_ranking=True); assert ok[0], ok[1]                                             # 真實 manifest 通過

def test_finalize_with_triggers():
    tmp = Path(tempfile.mkdtemp()); out = tmp / 'o'; (out / 'raw_outputs').mkdir(parents=True)
    rows = {'X': dict(trigger=False, C1=True, C2=False, C3=True, rescue_final=20, current_final=20, actual_ticker='X', structural_score_advantage=3.0, sar_gap=.06),
            'Y': dict(trigger=True, C1=True, C2=True, C3=True, rescue_final=29, current_final=19, actual_ticker='Y', structural_score_advantage=13.4, sar_gap=.051)}
    for tk, r in rows.items(): (out / 'raw_outputs' / tk).mkdir(); (out / 'raw_outputs' / tk / 'rescue.json').write_text(json.dumps(r))
    (out / 'raw_outputs' / 'index.json').write_text('{}'); (out / 'execution_record.json').write_text(json.dumps(dict(status='RAW_OUTPUTS_WRITTEN_PENDING_COMMIT', actual_tickers=['X', 'Y'], raw_outputs_index_sha256=V.sha256_file(out / 'raw_outputs' / 'index.json'))))
    s = V.finalize(out, 'b' * 40, check_git=False, log=lambda s: None)
    assert s['trigger_count'] == 1 and s['trigger_tickers'] == ['Y'] and s['VALIDATION_STATUS'] == 'MANUAL_REVIEW_REQUIRED' and s['triggers'][0]['rescue_final'] == 29 and 'PASS' not in json.dumps(s['VALIDATION_STATUS'])
    (out / 'execution_record.json').write_text(json.dumps(dict(status='RAW_OUTPUTS_WRITTEN_PENDING_COMMIT', actual_tickers=['X'], raw_outputs_index_sha256=V.sha256_file(out / 'raw_outputs' / 'index.json'))))
    assert V.finalize(out, 'c' * 40, check_git=False, log=lambda s: None)['VALIDATION_STATUS'] == 'INSUFFICIENT_VALIDATION'
    try: V.finalize(out, 'd' * 40, check_git=False, log=lambda s: None); assert False
    except AssertionError as e: assert 'finalize' in str(e)                                                                    # 已 finalize 不可重複

def test_no_production_file_changes():
    for f, h in MANIFEST['production']['file_sha256_at_production_commit'].items(): assert hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == h, f
    forbidden = ('core/', 'app.py', 'data/', 'README.md', 'research/', 'experiments/holdout_v22/', 'experiments/final_rules/', 'experiments/sar_confidence/', 'experiments/rescue_validation/freeze_manifest')
    for base in ('9ef4ef4', V.FREEZE_COMMIT):
        if subprocess.run(['git', 'cat-file', '-e', base], cwd=ROOT, capture_output=True).returncode: continue
        ch = subprocess.run(['git', 'diff', '--name-only', base], cwd=ROOT, capture_output=True, text=True).stdout.split() + subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, capture_output=True, text=True).stdout.split()
        bad = [f for f in ch if f.startswith(forbidden) and not (base == V.FREEZE_COMMIT and f == 'experiments/sar_confidence/sar_confidence_interpretation.md')]; assert not bad, (base, bad)
    ok, bad = V.verify_manifest_immutable(ROOT)
    if ok is not None: assert ok, bad
    import ast; tree = ast.parse((HERE / 'rescue_rule.py').read_text(encoding='utf-8')); assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]      # 獨立實作：不 import 任何模組（含 core、sar_confidence）

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print(n, flush=True); f()
    print('PASS: rescue validation run tests')
