"""freeze_suitability 的測試（只讀 metadata 與既有基準；不連網）。用法：python experiments/suitability_validation/test_freeze_suitability.py"""
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path[:0] = [str(HERE)]
import freeze_suitability as F
M = json.loads((HERE / 'freeze_manifest.json').read_text(encoding='utf-8'))
def check(c, msg): print(('PASS ' if c else 'FAIL ') + msg); assert c, msg
check(M['PRICE_DATA_ACCESSED'] is False and M['RESULTS_GENERATED'] is False, 'pre-open 旗標')
check(M['screening_pool'][0]['rank'] == 151 and len(M['screening_pool']) == 288 and all(x['sha256'] == hashlib.sha256((M['source']['ranking_seed'] + x['ticker']).encode()).hexdigest() for x in M['screening_pool']), '篩選池＝排名 151–438，SHA 可重算')
check(not set(M['excluded_ranks_1_150']) & {x['ticker'] for x in M['screening_pool']} and len(M['excluded_ranks_1_150']) == 150, '排名 1–150 全部排除')
check(M['strata']['Q1'] < M['strata']['Q3'] and M['strata']['n_total'] == 30, '分層門檻與樣本數')
src = (HERE / 'freeze_suitability.py').read_text(encoding='utf-8'); code = '\n'.join(l for l in src.splitlines() if not l.lstrip().startswith(('#', '"""')))
check(not any(b in code for b in ('fetch_yahoo(', 'urllib', 'yfinance', 'compute_metrics(')), '凍結程式沒有任何價格存取')
re = F.build(); re.pop('production'); m2 = dict(M); m2.pop('production')
check(re == m2, '重算 manifest（不含 base commit）與存檔相同')
print('ALL PASS')
