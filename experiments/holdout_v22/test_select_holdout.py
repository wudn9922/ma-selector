"""證明「選樣／hash 程序」是確定性的、獨立可驗證的，且沒有碰價格資料。純本機測試，不連網。
用法：python experiments/holdout_v22/test_select_holdout.py"""
import json, random, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import select_holdout as sh

M = json.loads((HERE / 'freeze_manifest.json').read_text(encoding='utf-8'))
def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

symbols, cols = sh.read_constituents(); universe = sh.load_universe(sh.PROD_COMMIT); hold = [t for v in sh.HISTORICAL_HOLDOUTS.values() for t in v]
r1, e1 = sh.eligible_ranked(symbols, universe, hold)
# 1) 重複執行、輸入順序打亂：結果相同
r2, _ = sh.eligible_ranked(list(symbols), universe, hold); check(r1 == r2, '同一輸入重複執行 → 排名完全相同')
for seed in (1, 2, 3):
    s = list(symbols); random.Random(seed).shuffle(s); check(sh.eligible_ranked(s, universe, hold)[0] == r1, f'輸入順序打亂（seed {seed}）→ 排名不變')
check(sh.eligible_ranked(symbols + symbols[:50], universe, hold)[0] == r1, '名單重複列出 → 排名不變')
# 2) 全新 process 重跑
out = subprocess.run([sys.executable, str(HERE / 'select_holdout.py'), '--print'], capture_output=True, text=True).stdout.split('\n')
check([l.split()[1] for l in out if l.strip()] == [r['ticker'] for r in r1[:sh.N_RANKED]], '全新 process 重跑 → 前 30 名相同')
# 3) hash 公式：用外部工具 sha256sum 獨立驗證前 12 名與最後一名
for r in r1[:12] + [r1[-1]]:
    ext = subprocess.run(['sha256sum'], input=(sh.SEED + r['ticker']).encode(), capture_output=True).stdout.decode().split()[0]
    check(ext == r['sha256'], f"sha256sum 獨立驗證 {r['ticker']}")
check(sh.SEED == 'MA_SELECTOR_V22_FINAL_HOLDOUT_2026-09-30|', 'seed 字串與凍結規格逐字相同')
check([r['sha256'] for r in r1] == sorted(r['sha256'] for r in r1), '排名依完整十六進位 hash 遞增')
# 4) manifest 與程序輸出一致
check(M['PRIMARY_8'] == [r['ticker'] for r in r1[:8]], 'manifest 的 PRIMARY 8 ＝ 排名前 8')
check(M['FALLBACK_ORDER'] == [r['ticker'] for r in r1[8:30]], 'manifest 的 FALLBACK 順序 ＝ 排名第 9–30')
check(len(M['ranking']['ranked_first_30']) == 30 and len(M['FALLBACK_ORDER']) >= 12, '至少儲存前 20 名（實際 30）')
check(M['ranking']['ranked_first_30'] == r1[:30] or all(a['ticker'] == b['ticker'] and a['sha256'] == b['sha256'] for a, b in zip(M['ranking']['ranked_first_30'], r1)), 'manifest 的排名內容與重算相同')
# 5) 合格條件
sel = set(M['PRIMARY_8'] + M['FALLBACK_ORDER'])
check(all(t.isalpha() and t.isupper() and t.isascii() for t in sel), '所選 ticker 都只含大寫英文字母')
check(not (sel & set(universe)), '所選 ticker 不在 core/universe.py（83 檔）')
check(not (sel & set(hold)), '所選 ticker 不在任何歷史 holdout')
check(sel <= set(symbols), '所選 ticker 都在取得的 S&P 500 名單中')
check(len(universe) == 83 and len(M['exclusions']['core_universe_83']) == 83, '排除 universe 為 83 檔')
check(len(sel) == 30 and len(set(M['PRIMARY_8'])) == 8, 'PRIMARY 8 檔互不重複')
# 6) 原始檔完整性與「沒有價格資料」
check(sh.sha256_bytes(sh.RAW.read_bytes()) == M['source']['saved_raw_file_sha256'], '儲存的原始成分股檔 SHA-256 與 manifest 相同')
check(cols == sh.META_COLUMNS, f'原始檔只有 metadata 欄位：{cols}')
check(M['PRICE_DATA_ACCESSED'] is False and M['HOLDOUT_RESULTS_GENERATED'] is False, 'PRICE_DATA_ACCESSED=false、HOLDOUT_RESULTS_GENERATED=false')
files = sorted(p.name for p in HERE.iterdir() if p.name != '__pycache__')
check(files == ['freeze_manifest.json', 'freeze_manifest.md', 'select_holdout.py', 'sp500_constituents_raw.csv', 'test_select_holdout.py'], f'資料夾內沒有價格資料或結果檔：{files}')
# 7) production 檔案 hash（若歷史中有該 commit）
have = subprocess.run(['git', 'cat-file', '-e', sh.PROD_COMMIT + '^{commit}'], cwd=sh.ROOT).returncode == 0
if have:
    for f, h in M['production']['file_sha256_at_production_commit'].items(): check(sh.blob_sha(f) == h, f'production commit 的 {f} hash 與 manifest 相同')
    check(subprocess.run(['git', 'rev-parse', sh.PROD_COMMIT + '^{tree}'], cwd=sh.ROOT, capture_output=True, text=True).stdout.strip() == sh.PROD_TREE, 'production tree 與 manifest 相同')
    for f in M['production']['file_sha256_at_production_commit']:
        if f != 'data/reference.parquet': continue
    same = all(sh.sha256_bytes((sh.ROOT / f).read_bytes()) == h for f, h in M['production']['file_sha256_at_production_commit'].items())
    check(same, '目前工作目錄的 production 檔案（含 reference.parquet）與 production commit 逐位元組相同')
else: print('SKIP production commit 不在此 clone 的歷史中')
print('ALL PASS')
