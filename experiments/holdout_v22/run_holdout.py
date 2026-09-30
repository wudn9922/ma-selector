"""CURRENT_V22_FRESH_HOLDOUT_1 的第一次價格資料開封（一次性）。
只呼叫已凍結的 production 函式（core.data／metrics／score／select），只序列化它們現成的輸出；不設計任何新指標、評分或判斷。
順序：① 一次性守門 → ② manifest 不可變檢查 → ③ production integrity gate（在取得任何價格之前）→ ④ 抓資料與資料充足性（900 根、依凍結 FALLBACK 順序替補）
      → ⑤ 對「全部 8 檔」執行 production → ⑥ commit 前檢查 → ⑦ 才寫出 raw outputs 與 execution record。
本程式只印出執行狀態（ticker、bar 數、日期、是否足夠），不印任何 candidate／final／分數／報酬。
用法（GitHub Actions）：python experiments/holdout_v22/run_holdout.py"""
import argparse, hashlib, inspect, json, os, platform, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
BATCH = 'CURRENT_V22_FRESH_HOLDOUT_1'
FREEZE_COMMIT = 'f2893eed9a6ac21d7e9cf94a4d06f275bc920ff6'          # 建立 freeze manifest 的 commit（pre-registration evidence）
MANIFEST_FILES = ['experiments/holdout_v22/freeze_manifest.json', 'experiments/holdout_v22/freeze_manifest.md']
N_TARGET, MIN_BARS = 8, 900
PER_TICKER_FILES = ['bars.csv', 'metrics.csv', 'scores.csv', 'smoothed_structural_scores.csv', 'selection.json', 'meta.json']
FORBIDDEN_WORDS = ['human', 'review', 'ground_truth', 'coverage', 'large_miss']                      # 輸出中不得出現的人工判斷／評分欄位

def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def sha256_file(p): return sha256_bytes(Path(p).read_bytes())
def utcnow(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def git(args, root): return subprocess.run(['git'] + args, cwd=root, capture_output=True)

def clean(o):
    """把 production 現成輸出轉成 JSON 可存的型別（numpy → Python；NaN／inf → null）。不改數值。"""
    import numpy as np
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o); return None if f != f or f in (float('inf'), float('-inf')) else f
    if isinstance(o, (np.bool_,)): return bool(o)
    return o

def write_blocked(out_dir, status, details, price_accessed):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    rec = dict(batch=BATCH, status=status, details=details, price_data_accessed=price_accessed, holdout_results_generated=False, time_utc=utcnow())
    (Path(out_dir) / 'execution_blocked.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'); return rec

def verify_manifest_immutable(root, log):
    """freeze manifest 必須與 freeze commit 當時完全相同（pre-registration evidence）；無法驗證時回傳說明"""
    if git(['cat-file', '-e', FREEZE_COMMIT + '^{commit}'], root).returncode != 0: return None, 'freeze commit 不在此 clone 的歷史中，無法驗證'
    bad = []
    for f in MANIFEST_FILES:
        blob = git(['show', f'{FREEZE_COMMIT}:{f}'], root)
        if blob.returncode != 0 or sha256_bytes(blob.stdout) != sha256_file(root / f): bad.append(f)
    return (not bad), bad

def integrity_gate(manifest, root, log):
    """production 檔案 SHA-256 必須與 manifest 完全一致；一有不一致就回傳不一致清單（呼叫端必須在抓價格之前停止）"""
    want = manifest['production']['file_sha256_at_production_commit']; got, bad = {}, []
    for f, h in want.items():
        p = root / f; got[f] = sha256_file(p) if p.exists() else None
        if got[f] != h: bad.append(f)
    ref_ok = got.get('data/reference.parquet') == manifest['reference']['sha256']
    if not ref_ok and 'data/reference.parquet' not in bad: bad.append('data/reference.parquet')
    tree = git(['rev-parse', manifest['production']['commit'] + '^{tree}'], root)
    tree_ok = None if tree.returncode != 0 else tree.stdout.decode().strip() == manifest['production']['tree']
    if tree_ok is False: bad.append('production tree')
    return not bad, bad, got, tree_ok

def real_fetcher(tk):
    from core import data
    for k in range(4):
        try: return data.fetch_yahoo(tk)          # production 現有的資料抓取路徑
        except Exception as e: err = e; time.sleep(3 * (k + 1))
    raise RuntimeError(f'DATA_FETCH_FAILURE {tk}: {type(err).__name__}')

def run(asof, out_dir, manifest_path, root, fetcher, real=True, log=print):
    """回傳 (exit_code, status)。out_dir 只在所有檢查通過後才寫入 raw outputs。"""
    out_dir = Path(out_dir); t0 = utcnow()
    # ① 一次性守門
    if real and ((out_dir / 'execution_record.json').exists() or (out_dir / 'raw_outputs').exists()):
        log('ALREADY_OPENED：已有 execution record／raw outputs，拒絕重複開封（blocked 紀錄不算，因為 blocked 代表沒有產生結果）。'); return 0, 'ALREADY_OPENED'
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    assert manifest['batch'] == BATCH and manifest['PRICE_DATA_ACCESSED'] is False and manifest['HOLDOUT_RESULTS_GENERATED'] is False, 'manifest 不是 pre-open 狀態'
    # ② freeze manifest 不可變
    man_ok, info = verify_manifest_immutable(root, log)
    if man_ok is False: write_blocked(out_dir, 'BLOCKED_FREEZE_MANIFEST_CHANGED', {'changed_files': info}, False); log('BLOCKED_FREEZE_MANIFEST_CHANGED：' + str(info)); return 2, 'BLOCKED_FREEZE_MANIFEST_CHANGED'
    if man_ok is None and real: write_blocked(out_dir, 'BLOCKED_CANNOT_VERIFY_FREEZE_MANIFEST', {'reason': info}, False); log('BLOCKED：' + info); return 2, 'BLOCKED_CANNOT_VERIFY_FREEZE_MANIFEST'
    # ③ production integrity gate（此時尚未取得任何價格資料）
    ok, bad, got, tree_ok = integrity_gate(manifest, root, log)
    if not ok: write_blocked(out_dir, 'BLOCKED_PRODUCTION_DRIFT', {'mismatched': bad}, False); log('BLOCKED_PRODUCTION_DRIFT：' + str(bad)); return 3, 'BLOCKED_PRODUCTION_DRIFT'
    log(f'PRODUCTION INTEGRITY：OK（{len(got)} 個檔案 hash 與 manifest 相同；tree {"OK" if tree_ok else "未驗證" if tree_ok is None else "不符"}）')
    sys.path.insert(0, str(root))
    import numpy as np, pandas as pd
    from core import data, metrics, score, select as sel
    # 凍結參數再確認（讀 production 程式自己的值，不改）
    assert sel.GAP == manifest['production']['frozen_parameters']['candidate_gap_default'] == 15 and [r[:3] for r in sel.RANGES] == [('短期', 15, 33), ('中期', 34, 45), ('長期', 46, 110)], 'production 參數與 manifest 不符'
    primary, fallback = manifest['PRIMARY_8'], manifest['FALLBACK_ORDER']; attempts, accepted, chain = [], [], {}
    fb_i = 0; pool = {}
    def evaluate(tk, role):
        raw = fetcher(tk); df = data.normalize(raw, asof)                                # 只保留 ≤ ASOF 的已完成日線
        rec = dict(ticker=tk, role=role, fetched_rows_total=int(len(raw)), bars_after_asof_dropped=int(len(raw) - len(df)), n_bars=int(len(df)),
                   first_date=str(df.date.iloc[0].date()) if len(df) else None, last_date=str(df.date.iloc[-1].date()) if len(df) else None, sufficient=bool(len(df) >= MIN_BARS))
        assert (not len(df)) or df.date.iloc[-1] <= pd.Timestamp(asof), 'cutoff 失敗'
        attempts.append(rec); pool[tk] = df; log(f"DATA {tk}: bars={rec['n_bars']} first={rec['first_date']} last={rec['last_date']} sufficient={rec['sufficient']}"); return rec
    # ④ 抓資料與替補（順序完全依 manifest；資料不足不算失敗；抓取失敗＝BLOCKED，不替補）
    try:
        for tk in primary:
            rec = evaluate(tk, 'PRIMARY')
            if rec['sufficient']: accepted.append(tk); continue
            chain[tk] = []
            while True:
                if fb_i >= len(fallback): write_blocked(out_dir, 'BLOCKED_FALLBACK_EXHAUSTED', {'primary': tk}, True); log('BLOCKED_FALLBACK_EXHAUSTED'); return 6, 'BLOCKED_FALLBACK_EXHAUSTED'
                fb = fallback[fb_i]; fb_i += 1; r2 = evaluate(fb, 'FALLBACK'); chain[tk].append(dict(ticker=fb, n_bars=r2['n_bars'], sufficient=r2['sufficient']))
                if r2['sufficient']: accepted.append(fb); break
    except RuntimeError as e:
        write_blocked(out_dir, 'BLOCKED_DATA_FETCH_FAILURE', {'message': str(e)}, True); log('BLOCKED_DATA_FETCH_FAILURE：' + str(e)); return 4, 'BLOCKED_DATA_FETCH_FAILURE'
    if len(accepted) != N_TARGET: write_blocked(out_dir, 'BLOCKED_NOT_8_COMPLETED', {'n': len(accepted)}, True); return 5, 'BLOCKED_NOT_8_COMPLETED'
    # ⑤ 對全部 8 檔執行 production（不顯示任何結果）
    ref = pd.read_parquet(root / 'data' / 'reference.parquet'); staged = {}
    try:
        for tk in accepted:
            df = pool[tk]; M = metrics.compute_metrics(df); S = score.score_table(M, ref); R = sel.select(df, S); P_, Ss = sel.smoothed_scores(S); suit = sel.suitability(S)
            staged[tk] = dict(df=df, M=M, S=S, R=R, smooth=pd.DataFrame({'period': P_, 'smoothed_structural_score': Ss}), suit=suit)
            log(f'PRODUCTION RUN {tk}: done')
    except Exception as e:
        write_blocked(out_dir, 'BLOCKED_PRODUCTION_ERROR', {'ticker': tk, 'error_type': type(e).__name__}, True); log(f'BLOCKED_PRODUCTION_ERROR {tk} {type(e).__name__}'); return 7, 'BLOCKED_PRODUCTION_ERROR'
    # ⑥ 寫到暫存區並做 commit 前檢查
    tmp = Path(tempfile.mkdtemp(prefix='holdout_stage_')); raw_dir = tmp / 'raw_outputs'; index = {}
    defaults = {k: (None if v.default is inspect._empty else v.default) for k, v in inspect.signature(sel.select).parameters.items() if k not in ('df', 'S')}
    for tk, x in staged.items():
        d = raw_dir / tk; d.mkdir(parents=True)
        x['df'].drop(columns='date').to_csv(d / 'bars.csv', index=False); x['M'].to_csv(d / 'metrics.csv', index=False); x['S'].to_csv(d / 'scores.csv', index=False); x['smooth'].to_csv(d / 'smoothed_structural_scores.csv', index=False)
        (d / 'selection.json').write_text(json.dumps(dict(ticker=tk, asof=asof, production_select_defaults_used=clean(defaults), selection=clean(x['R']), suitability_short_long=clean(x['suit'])), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        rec = next(a for a in attempts if a['ticker'] == tk)
        (d / 'meta.json').write_text(json.dumps(dict(ticker=tk, role=rec['role'], asof=asof, n_bars=rec['n_bars'], first_date=rec['first_date'], last_date=rec['last_date'], bars_sha256=sha256_file(d / 'bars.csv'),
                                                     price_source='core.data.fetch_yahoo (production path), range=5y, cut at ASOF'), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index[tk] = {f: sha256_file(d / f) for f in PER_TICKER_FILES}
    (raw_dir / 'index.json').write_text(json.dumps(index, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    _, _, got2, _ = integrity_gate(manifest, root, log)
    dirty = git(['status', '--porcelain', '--', 'core', 'data', 'research', 'experiments/holdout_v22/freeze_manifest.json', 'experiments/holdout_v22/freeze_manifest.md'], root).stdout.decode().strip()
    text_blob = ''.join((raw_dir / tk / f).read_text(encoding='utf-8').lower() for tk in accepted for f in ('selection.json', 'meta.json') ) + ''.join((raw_dir / tk / 'metrics.csv').read_text(encoding='utf-8')[:300].lower() for tk in accepted)
    checks = {'exactly_8_completed_stocks': len(accepted) == N_TARGET and len(set(accepted)) == N_TARGET,
              'each_stock_ge_900_bars': all(next(a for a in attempts if a['ticker'] == tk)['n_bars'] >= MIN_BARS for tk in accepted),
              'last_date_le_asof': all(next(a for a in attempts if a['ticker'] == tk)['last_date'] <= asof for tk in accepted),
              'production_hashes_still_match_freeze_manifest': got2 == got and all(got2[f] == h for f, h in manifest['production']['file_sha256_at_production_commit'].items()),
              'reference_sha_still_matches': got2.get('data/reference.parquet') == manifest['reference']['sha256'],
              'short_mid_long_all_completed': all(set(staged[tk]['R'].keys()) == {'短期', '中期', '長期'} and all('final' in staged[tk]['R'][nm] and len(staged[tk]['R'][nm]['cands']) >= 1 for nm in ('短期', '中期', '長期')) for tk in accepted),
              'raw_outputs_all_serialized': all((raw_dir / tk / f).exists() and (raw_dir / tk / f).stat().st_size > 0 for tk in accepted for f in PER_TICKER_FILES),
              'no_manual_review_fields': not any(w in text_blob for w in FORBIDDEN_WORDS),
              'no_holdout_accuracy_metrics_computed': True,           # 本程式沒有任何 candidate coverage／final accuracy／large miss 的計算（沒有 ground truth）
              'no_production_or_manifest_change_in_worktree': dirty == ''}
    if not all(checks.values()):
        write_blocked(out_dir, 'BLOCKED_PRE_COMMIT_CHECK_FAILED', {'failed_checks': [k for k, v in checks.items() if not v]}, True); log('BLOCKED_PRE_COMMIT_CHECK_FAILED：' + str([k for k, v in checks.items() if not v])); return 8, 'BLOCKED_PRE_COMMIT_CHECK_FAILED'
    # ⑦ 全部通過才寫入 repo 目錄
    import shutil; out_dir.mkdir(parents=True, exist_ok=True); shutil.copytree(raw_dir, out_dir / 'raw_outputs')
    record = dict(batch=BATCH, status='RAW_OUTPUTS_WRITTEN_PENDING_COMMIT', raw_output_commit_sha=None,
                  production=dict(commit=manifest['production']['commit'], tree=manifest['production']['tree'], hashes_verified=True, tree_verified=tree_ok, file_sha256_verified=got2),
                  reference_sha256=got2['data/reference.parquet'], asof=asof, price_data_accessed=True, holdout_results_generated=True,
                  freeze_manifest=dict(freeze_commit=FREEZE_COMMIT, unchanged_since_freeze_commit=man_ok, sha256={f: sha256_file(root / f) for f in MANIFEST_FILES}),
                  primary_requested=primary, fallback_order_frozen=fallback,
                  data_sufficiency=attempts, replacements=[dict(replaced_primary=p, chain=c, final_replacement=next((x['ticker'] for x in c if x['sufficient']), None)) for p, c in chain.items()],
                  actual_holdout_8=accepted, min_bars_required=MIN_BARS, pre_commit_checks=checks,
                  raw_output_dir='experiments/holdout_v22/raw_outputs', raw_outputs_index_sha256=sha256_file(out_dir / 'raw_outputs' / 'index.json'),
                  audit_notes=['bars.csv／metrics.csv／scores.csv 以 Python repr 寫出（可逐位元還原）；重讀時請用 pd.read_csv(..., float_precision="round_trip")，pandas 預設讀取器最後一位小數可能不同。',
                               'selection.json 是 core.select.select(df, score_table(compute_metrics(df), reference)) 的原樣輸出（NaN→null）；用 bars.csv 重算應完全相同。',
                               'bars.csv 是 core.data.fetch_yahoo 取得後以 ASOF 截斷的已完成日線（欄位 time,open,high,low,close,volume）。'],
                  no_review_no_ground_truth_note='原始輸出在使用者審閱之前產生並先 commit；本檔沒有任何 candidate／final／分數／報酬，也沒有人工判斷或 holdout 命中率。',
                  environment=dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__, github_run_id=os.environ.get('GITHUB_RUN_ID'), github_sha=os.environ.get('GITHUB_SHA')),
                  started_utc=t0, finished_utc=utcnow())
    (out_dir / 'execution_record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    log('ALL 8 RAW OUTPUTS WRITTEN；等待 commit（在 commit 之前不得檢視任何結果）'); return 0, 'RAW_OUTPUTS_WRITTEN_PENDING_COMMIT'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-29'); a = ap.parse_args()
    code, status = run(a.asof, HERE, HERE / 'freeze_manifest.json', ROOT, real_fetcher, real=True); print('STATUS:', status); sys.exit(code)

if __name__ == '__main__': main()
