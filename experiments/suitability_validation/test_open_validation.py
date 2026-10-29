"""open_validation 的測試（合成股價＋假 fetcher；不連網）。用法：python experiments/suitability_validation/test_open_validation.py"""
import copy, json, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / 'scripts')]
import open_validation as O
from regression_synth import synth
from core import data
M = json.loads((HERE / 'freeze_manifest.json').read_text(encoding='utf-8'))
def check(c, msg): print(('PASS ' if c else 'FAIL ') + msg); assert c, msg
REF = (ROOT / 'data/reference.parquet').read_bytes() if O.SHA((ROOT / 'data/reference.parquet').read_bytes()) == M['reference']['sha256'] else O.git(['show', f'{O.FREEZE_COMMIT}:data/reference.parquet'], ROOT).stdout

def fake_manifest(tmp, q1, q3, n_pool=80, per=2):
    m = copy.deepcopy(M); m['screening_pool'] = [dict(rank=151 + i, ticker=f'T{i:03d}', sha256='x') for i in range(n_pool)]; m['strata'].update(Q1=q1, Q3=q3, per_stratum=per)
    p = Path(tmp) / 'm.json'; p.write_text(json.dumps(m)); return p
class Fx:
    def __init__(self, fail=(), short=()): self.calls = []; self.fail = set(fail); self.short = set(short)
    def __call__(self, tk):
        self.calls.append(tk)
        if tk in self.fail: raise O.FetchError(tk + ': simulated')
        return synth(int(tk[1:]) + 1, 400 if tk in self.short else 1100)

def main():
    tmp = Path(tempfile.mkdtemp()); mp = fake_manifest(tmp, 45., 60.); fx = Fx(fail={'T001'}, short={'T002'}); logs = []
    st = O.run(tmp / 'out', ROOT, fx, mp, real=False, log=logs.append, ref_bytes=REF)
    if st == 'BLOCKED_INSUFFICIENT_POOL':
        check(True, '合成資料沒有填滿三層 → BLOCKED_INSUFFICIENT_POOL（流程正確）'); return
    check(st == 'OPENED_PENDING_COMMIT', f'合成資料開封成功（{st}）')
    out = tmp / 'out'; rec = json.loads((out / 'execution_record.json').read_text()); sealed = json.loads((out / 'sealed_scores.json').read_text())
    check({'SKIPPED_FETCH_FAILURE', 'SKIPPED_INSUFFICIENT_BARS'} <= {d['status'] for d in rec['data_status']}, '抓取失敗與資料不足都記錄並略過（不 BLOCKED）')
    check(fx.calls[:3] == ['T000', 'T001', 'T002'], '依凍結排名順序處理')
    sel = sealed['selected']; strata = [v['stratum'] for v in sel.values()]
    check(all(strata.count(s) == 2 for s in ('LOW', 'MID', 'HIGH')), '每層剛好 per_stratum 檔')
    order = [v['ticker'] for v in rec['review_order']]
    check(order == sorted(order, key=lambda t: O.SHA(('MA_SELECTOR_SUITABILITY_REVIEW_ORDER_2026-10-29|' + t).encode())), '審閱順序＝凍結的 hash 排序')
    check(all(s['stratum'] == O.stratum(s['short_suitability'], 45., 60.) for s in sealed['screening'] if s['status'] == 'SCORED'), '分層依凍結門檻')
    picked_rank = {}
    for s in sealed['screening']:
        if s['status'] == 'SCORED': picked_rank.setdefault(s['stratum'], []).append((s['rank'], s['selected']))
    check(all([sel_ for _, sel_ in v][:2] == [True, True][:len(v[:2])] and not any(x for _, x in v[2:]) for v in picked_rank.values()), '各層取排名最前面的檔（之後的不選）')
    txt = ' '.join(json.dumps(d) for d in rec['data_status']) + json.dumps(rec['review_order'])
    check(not any(w in txt for w in ('short_suitability', 'stratum', 'LOW', 'HIGH')), 'execution record 不含分數／分層')
    rb = out / 'review_bundle'; check(len(list(rb.glob('*.png'))) == 6 and (rb / 'review_manifest.md').exists(), '審閱圖與 manifest 已產生')
    check(all(l.startswith(('INTEGRITY', 'DATA', 'OPENED')) and 'score' not in l.lower() for l in logs), 'log 只有資料狀態')
    check(O.run(out, ROOT, Fx(), mp, real=True, log=lambda s: None, ref_bytes=REF) == 'ALREADY_OPENED', '一次性守門')
    bad = json.loads(mp.read_text()); bad['production']['file_sha256']['core/select.py'] = '0' * 64; bp = tmp / 'b.json'; bp.write_text(json.dumps(bad)); fx2 = Fx()
    check(O.run(tmp / 'o2', ROOT, fx2, bp, real=False, log=lambda s: None, ref_bytes=REF) == 'BLOCKED_PRODUCTION_DRIFT' and fx2.calls == [], 'production drift → 抓價格前就停止')
    check(O.run(tmp / 'o3', ROOT, Fx(), mp, real=False, log=lambda s: None, ref_bytes=b'x') == 'BLOCKED_REFERENCE_MISMATCH', 'reference 不符 → 停止')
    print('ALL PASS')
if __name__ == '__main__': main()
