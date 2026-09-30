"""freeze_rescue_validation 的測試（只讀 metadata；不連網）。用法：python experiments/rescue_validation/test_freeze_rescue_validation.py"""
import hashlib, json, re, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE)]
import freeze_rescue_validation as F
M = json.loads((HERE / 'freeze_manifest.json').read_text(encoding='utf-8')); HM = json.loads((ROOT / 'experiments/holdout_v22/freeze_manifest.json').read_text(encoding='utf-8'))
SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def test_flags_and_source():
    assert M['PRICE_DATA_ACCESSED'] is False and M['RESULTS_GENERATED'] is False
    assert M['source']['saved_raw_file_sha256'] == SHA(ROOT / 'experiments/holdout_v22/sp500_constituents_raw.csv') == HM['source']['saved_raw_file_sha256']
    assert M['ranking']['hash_seed'] == HM['ranking']['hash_seed'] == 'MA_SELECTOR_V22_FINAL_HOLDOUT_2026-09-30|' and M['asof'] == '2026-09-29'
    assert M['holdout_freeze_manifest_sha256'] == SHA(ROOT / 'experiments/holdout_v22/freeze_manifest.json')

def test_ranking():
    v = M['VALIDATION_TICKERS']; assert M['VALIDATION_N'] == 100 == len(v) and [x['rank'] for x in v] == list(range(31, 131))
    tk = [x['ticker'] for x in v]; assert len(set(tk)) == 100
    for x in v + M['FALLBACK_ORDER']: assert x['sha256'] == hashlib.sha256((M['ranking']['hash_seed'] + x['ticker']).encode()).hexdigest()
    allr = v + M['FALLBACK_ORDER']; assert [x['sha256'] for x in allr] == sorted(x['sha256'] for x in allr) and [x['rank'] for x in M['FALLBACK_ORDER']] == list(range(131, 151))
    first30 = HM['ranking']['ranked_first_30']; assert first30[-1]['sha256'] < v[0]['sha256']                              # 排名接續
    used = {x['ticker'] for x in first30}; assert not used & set(tk) and not used & {x['ticker'] for x in M['FALLBACK_ORDER']}
    excl = set(HM['exclusions']['core_universe_83']) | {t for l in HM['exclusions']['historical_holdouts_contaminated'].values() for t in l}
    assert not excl & (set(tk) | {x['ticker'] for x in M['FALLBACK_ORDER']}) and all(re.fullmatch(r'[A-Z]+', t) for t in tk)
    assert set(tk) <= set(HM['source']['raw_constituent_tickers'])

def test_production_frozen():
    p = M['production']; assert p['commit'] == HM['production']['commit'] and p['tree'] == HM['production']['tree'] and M['reference']['sha256'] == HM['reference']['sha256']
    for f, h in p['file_sha256_at_production_commit'].items(): assert SHA(ROOT / f) == h, f
    assert p['file_sha256_at_production_commit']['data/reference.parquet'] == M['reference']['sha256']
    for f, h in M['diagnostic_evidence']['files_sha256'].items(): assert SHA(ROOT / f) == h, f

def test_rule_text():
    R = M['STRUCTURAL_RESCUE_10PT_10PP']
    assert len(R['conditions']) == 3 and '+ 10.0 points' in R['conditions'][1] and '− 10 percentage points' in R['conditions'][2] and '永久固定' in R['thresholds_permanently_fixed']
    assert 'INSUFFICIENT_VALIDATION' in M['next_stage_plan']['zero_trigger'] and M['diagnostic_evidence']['confirmed']['POSTHOC_10PT_10PP_finals_changed_on_83_development_stocks'] == 0
    assert any('5 percentage points' in x for x in M['CURRENT_RULE_B']['definition'])

def test_reproducible():
    assert F.build() == M and F.to_md(M) == (HERE / 'freeze_manifest.md').read_text(encoding='utf-8')          # 重算與已存檔完全相同

def test_no_price_access():
    src = (HERE / 'freeze_rescue_validation.py').read_text(encoding='utf-8'); code = '\n'.join(l for l in src.splitlines() if not l.strip().startswith('#'))
    for bad in ('fetch_yahoo', 'yfinance', 'urllib', 'requests', 'query1.finance', 'read_parquet', 'raw_outputs', 'core.select', 'from core', 'import core'): assert bad not in code.replace("'core/select.py'", ''), bad
    assert not list(HERE.glob('*.csv')) and not list(HERE.glob('*.parquet'))
    if not (HERE / 'execution_record.json').exists(): assert not list(HERE.glob('raw_outputs'))                                        # freeze 階段：本目錄沒有任何價格／結果檔（開封之後才會有 raw_outputs）

def test_no_forbidden_changes():
    base = '1359ea2'                                                                                                          # 開始此階段前的 commit
    if subprocess.run(['git', 'cat-file', '-e', base], cwd=ROOT, capture_output=True).returncode != 0: return
    ch = subprocess.run(['git', 'diff', '--name-only', base], cwd=ROOT, capture_output=True, text=True).stdout.split() + subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, capture_output=True, text=True).stdout.split()
    bad = [f for f in ch if f.startswith(('core/', 'app.py', 'data/', 'README.md', 'experiments/holdout_v22/', 'experiments/final_rules/', 'regression/', 'research/'))]; assert not bad, bad

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print(n); f()
    print('PASS: rescue validation freeze tests')
