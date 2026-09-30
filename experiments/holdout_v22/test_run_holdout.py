"""run_holdout.py 的行為測試（只用合成股價、輸出全部寫到暫存目錄；不碰 repo、不取得真實價格）。
檢查：正常流程、資料不足依凍結順序替補、production hash 不符時在抓價格之前停止、抓取失敗不替補、一次性守門、序列化忠實度、沒有 production 改動。
用法：python experiments/holdout_v22/test_run_holdout.py"""
import json, subprocess, sys, tempfile
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / 'scripts')]
import run_holdout as rh
from regression_synth import synth

MANIFEST = HERE / 'freeze_manifest.json'; M = json.loads(MANIFEST.read_text(encoding='utf-8')); PRIMARY, FALLBACK = M['PRIMARY_8'], M['FALLBACK_ORDER']
def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

def make_fetcher(short=None, fail=None, n=1300):
    short = short or {}; calls = []
    def f(tk):
        calls.append(tk)
        if fail and tk == fail: raise RuntimeError(f'DATA_FETCH_FAILURE {tk}')
        df = synth(abs(hash(tk)) % 10000, short.get(tk, n)); df['time'] = pd.bdate_range(end='2026-09-30', periods=len(df)).strftime('%Y-%m-%d')   # 含 2026-09-30（应被 ASOF 截掉）
        from core import data; return data.normalize(df)
    f.calls = calls; return f

def new_dir(): return Path(tempfile.mkdtemp(prefix='hold_test_'))

# ── 1) 正常流程 ──
fx = make_fetcher(); out = new_dir(); logs = []
code, status = rh.run('2026-09-29', out, MANIFEST, ROOT, fx, real=False, log=logs.append)
check(code == 0 and status == 'RAW_OUTPUTS_WRITTEN_PENDING_COMMIT', f'正常流程完成：{status}')
rec = json.loads((out / 'execution_record.json').read_text(encoding='utf-8'))
check(fx.calls == PRIMARY, '抓取順序＝凍結的 PRIMARY 順序，沒有多抓')
check(rec['actual_holdout_8'] == PRIMARY and rec['replacements'] == [], '沒有資料不足 → 沒有替補')
check(all(a['bars_after_asof_dropped'] == 1 and a['last_date'] <= '2026-09-29' for a in rec['data_sufficiency']), '2026-09-30 的 bar 被截掉，last_date ≤ ASOF')
check(all(v for v in rec['pre_commit_checks'].values()) and len(rec['pre_commit_checks']) == 10, 'commit 前檢查全部通過')
check(rec['price_data_accessed'] is True and rec['holdout_results_generated'] is True and rec['raw_output_commit_sha'] is None, 'execution record 旗標正確（commit SHA 留待 commit 後補）')
check(rec['production']['hashes_verified'] is True and rec['reference_sha256'] == M['reference']['sha256'], 'production／reference hash 已驗證')
for tk in PRIMARY: check(all((out / 'raw_outputs' / tk / f).stat().st_size > 0 for f in rh.PER_TICKER_FILES), f'{tk}：6 個 raw output 檔都已序列化')
idx = json.loads((out / 'raw_outputs' / 'index.json').read_text(encoding='utf-8'))
check(all(rh.sha256_file(out / 'raw_outputs' / tk / f) == h for tk, d in idx.items() for f, h in d.items()), 'index.json 的檔案 hash 都與檔案相符')
txt = '\n'.join(logs); check(not any(w in txt for w in ['短期', '中期', '長期', 'final', 'candidate', '分數']), '執行紀錄沒有任何 candidate／final／分數字樣')
check(not any(w in (out / 'execution_record.json').read_text(encoding='utf-8') for w in ['均線', '反手報酬', '結構分', '"final"', '"cands"', '簡單報酬']), 'execution record 沒有任何結果欄位（只有 metadata）')
# 序列化忠實度：selection.json ＝ production 直接重算的結果（只是序列化）
from core import data, metrics, score, select as sel
tk = PRIMARY[0]; df = pd.read_csv(out / 'raw_outputs' / tk / 'bars.csv', float_precision='round_trip'); df = data.normalize(df)   # 逐位元還原需要 round_trip 讀法
S = score.score_table(metrics.compute_metrics(df), pd.read_parquet(ROOT / 'data' / 'reference.parquet')); R = rh.clean(sel.select(df, S))
saved = json.loads((out / 'raw_outputs' / tk / 'selection.json').read_text(encoding='utf-8'))
check(saved['selection'] == R, '序列化的 selection.json 與 production 用同一份 bars 重算的結果完全相同')
check(saved['production_select_defaults_used']['gap'] == 15 and saved['production_select_defaults_used']['final_rule'] == 'structural' and saved['production_select_defaults_used']['method'] == 'sar', '記錄了 production select 的預設參數（gap=15、sar、structural＝Rule B）')

# ── 2) 資料不足 → 依凍結 FALLBACK 順序替補（WBD 不足、第一個替補 PRU 也不足 → LH）──
fx = make_fetcher(short={'WBD': 500, FALLBACK[0]: 700}); out = new_dir()
code, status = rh.run('2026-09-29', out, MANIFEST, ROOT, fx, real=False, log=lambda *_: None); rec = json.loads((out / 'execution_record.json').read_text(encoding='utf-8'))
check(code == 0 and rec['actual_holdout_8'] == [PRIMARY[0], FALLBACK[1]] + PRIMARY[2:], f'替補依凍結順序：WBD → {FALLBACK[0]}（不足）→ {FALLBACK[1]}')
# 造資料不足用的 700 根含 2026-09-30 那根，截斷後有效 bar 數是 699
check(rec['replacements'] == [dict(replaced_primary='WBD', chain=[dict(ticker=FALLBACK[0], n_bars=699, sufficient=False), dict(ticker=FALLBACK[1], n_bars=rec['replacements'][0]['chain'][1]['n_bars'], sufficient=True)], final_replacement=FALLBACK[1])], 'replacement chain 完整記錄')
check(fx.calls == PRIMARY[:2] + FALLBACK[:2] + PRIMARY[2:], '抓取順序完全照 manifest（沒有人工挑選）')
# ── 3) production hash 不符 → 在取得任何價格之前停止 ──
bad = json.loads(MANIFEST.read_text(encoding='utf-8')); bad['production']['file_sha256_at_production_commit']['core/select.py'] = '0' * 64
bp = new_dir() / 'm.json'; bp.write_text(json.dumps(bad), encoding='utf-8'); fx = make_fetcher(); out = new_dir()
code, status = rh.run('2026-09-29', out, bp, ROOT, fx, real=False, log=lambda *_: None)
check(code == 3 and status == 'BLOCKED_PRODUCTION_DRIFT' and fx.calls == [] and not (out / 'raw_outputs').exists(), 'hash 不符 → BLOCKED_PRODUCTION_DRIFT，fetcher 一次都沒被呼叫，沒有 raw outputs')
check(json.loads((out / 'execution_blocked.json').read_text(encoding='utf-8'))['price_data_accessed'] is False, 'blocked 紀錄：price_data_accessed=false')
# ── 4) 抓取失敗 → BLOCKED，不替補 ──
fx = make_fetcher(fail='ELV'); out = new_dir(); code, status = rh.run('2026-09-29', out, MANIFEST, ROOT, fx, real=False, log=lambda *_: None)
check(code == 4 and status == 'BLOCKED_DATA_FETCH_FAILURE' and fx.calls == PRIMARY[:5] and not (out / 'raw_outputs').exists(), '抓取失敗 → BLOCKED，沒有替補、沒有 raw outputs')
# ── 5) 一次性守門 ──
out = new_dir(); (out / 'execution_record.json').write_text('{}', encoding='utf-8'); fx = make_fetcher(); code, status = rh.run('2026-09-29', out, MANIFEST, ROOT, fx, real=True, log=lambda *_: None)
check(status == 'ALREADY_OPENED' and fx.calls == [], '已有 execution record → 拒絕重複開封，沒有抓任何資料')
# ── 6) 沒有 production 改動 ──
check(subprocess.run(['git', 'status', '--porcelain', '--', 'core', 'data', 'research', 'experiments/holdout_v22/freeze_manifest.json', 'experiments/holdout_v22/freeze_manifest.md'], cwd=ROOT, capture_output=True, text=True).stdout.strip() == '', 'core／data／research／freeze manifest 沒有被修改')
check(not (HERE / 'raw_outputs').exists() and not (HERE / 'execution_record.json').exists(), '測試沒有在 repo 內留下任何 raw outputs 或 execution record')
print('ALL PASS')
