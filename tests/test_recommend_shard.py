"""scripts/build_recommendations.py 的分批（--shard／--max-missing／--tickers-file／--no-prune）測試；用封存的 bars，不連 Yahoo。
用法：python tests/test_recommend_shard.py"""
import json, sys, tempfile, zlib
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import build_recommendations as br
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
RAW = ROOT / 'experiments' / 'rescue_validation' / 'raw_outputs'
TK = sorted(p.name for p in RAW.iterdir() if p.is_dir())[:9]

def _bars(d):
    d.mkdir(parents=True, exist_ok=True)
    for tk in TK: pd.read_csv(RAW / tk / 'bars.csv').to_csv(d / f'{tk}.csv', index=False)

def _mtimes(out): return {f.stem: f.stat().st_mtime_ns for f in out.glob('*.json') if f.name != 'index.json'}

def test_shard_helpers():
    check(all(br.shard_of(t, 3) == zlib.crc32(t.encode()) % 3 for t in TK), 'shard_of＝crc32 % N（與清單內容、順序無關）')
    check(br.parse_shard('1/3') == (1, 3) and br.parse_shard('all') is None and br.parse_shard(None) is None, "parse_shard：'K/N'、'all'、None")
    for bad in ('3/3', '-1/3', '0/0', 'x'):
        try: br.parse_shard(bad); ok = False
        except ValueError: ok = True
        check(ok, f'parse_shard 拒絕 {bad!r}')

def test_plan():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp); mine = [t for t in TK if br.shard_of(t, 3) == 0]; others = [t for t in TK if t not in mine]
        todo, b = br.plan(TK, out, (0, 3), 0); check(todo == mine and b['missingAdded'] == 0 and b['missingLeft'] == len(others), f'沒有舊檔、max-missing 0 → 只算本批 {len(mine)} 檔')
        todo, b = br.plan(TK, out, (0, 3), 1); check(todo == sorted(mine + others[:1]) and b['missingAdded'] == 1 and b['missingLeft'] == len(others) - 1, 'max-missing 1 → 本批＋1 檔缺檔（依清單順序）')
        todo, b = br.plan(TK, out, (0, 3), -1); check(todo == TK and b['missingAdded'] == len(others), 'max-missing -1 → 本批＋全部缺檔')
        for t in others: (out / f'{t}.json').write_text('{}')
        todo, b = br.plan(TK, out, (0, 3), -1); check(todo == mine and b['missingAdded'] == 0, '其他批已有檔 → 只算本批')
        todo, b = br.plan(TK, out, None, 0); check(todo == TK and b['shard'] is None, '不分批 → 全部（同過去）')

def test_batch_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); bd, out = tmp / 'bars', tmp / 'out'; _bars(bd)
        lst = tmp / 'tickers.txt'; lst.write_text('# 全市場清單\n' + '\n'.join(TK) + '\n\n')
        mine = {t for t in TK if br.shard_of(t, 3) == 1}
        br.main(['--tickers-file', str(lst), '--bars-dir', str(bd), '--out', str(out), '--workers', '2', '--shard', '1/3', '--max-missing', '0'])
        idx = json.loads((out / 'index.json').read_text())
        check(set(_mtimes(out)) == mine and idx['processed'] == len(mine) and idx['requested'] == len(TK), f'第一批：只產生本批 {len(mine)} 檔；requested＝清單 {len(TK)} 檔')
        check(idx['refresh'] == dict(shard=1, shards=3, inShard=len(mine), missingAdded=0, missingLeft=len(TK) - len(mine)), f"index.refresh 記錄分批：{idx['refresh']}")
        br.main(['--tickers-file', str(lst), '--bars-dir', str(bd), '--out', str(out), '--workers', '2', '--shard', '2/3', '--max-missing', '-1'])
        t1 = _mtimes(out); idx = json.loads((out / 'index.json').read_text())
        check(set(t1) == set(TK) and len(idx['symbols']) == len(TK), 'shard 2 ＋全部缺檔 → 清單內每檔都有檔案，index 全列')
        check(sorted(s['ticker'] for s in idx['symbols'] if s['fresh']) == sorted(t for t in TK if t not in mine), 'fresh 只標這次重算的（本批＋缺檔），第一批沿用的標 False')
        br.main(['--tickers-file', str(lst), '--bars-dir', str(bd), '--out', str(out), '--workers', '2', '--shard', '1/3', '--max-missing', '-1'])
        t2 = _mtimes(out)
        check(all((t2[t] != t1[t]) == (t in mine) for t in TK), '再跑 shard 1：只改寫本批的檔，其他批的檔不動')
        r = json.loads((out / f'{sorted(mine)[0]}.json').read_text())
        check(any('previousFinal' in g and g['previousFinal'] is not None for g in r['ranges']), '重算時讀到上一次的檔當 prev（previousFinal 有值）')
        (out / 'ZZZZ.json').write_text('{}')
        br.main(['--tickers', *TK[:2], '--bars-dir', str(bd), '--out', str(out), '--workers', '1', '--shard', '0/3', '--max-missing', '0', '--no-prune'])
        check((out / 'ZZZZ.json').exists() and set(TK) <= set(_mtimes(out)), '--no-prune：清單外的舊檔保留（清單不完整時不誤刪）')
        br.main(['--tickers-file', str(lst), '--bars-dir', str(bd), '--out', str(out), '--workers', '1', '--shard', '0/3', '--max-missing', '0'])
        check(not (out / 'ZZZZ.json').exists() and set(_mtimes(out)) == set(TK), '預設：清單外的舊檔刪除，清單內全保留')

if __name__ == '__main__':
    test_shard_helpers(); test_plan(); test_batch_end_to_end(); print('ALL PASS')
