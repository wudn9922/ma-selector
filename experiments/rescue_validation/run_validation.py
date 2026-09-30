"""STRUCTURAL_RESCUE_FRESH_VALIDATION_100 的第一次價格資料開封（一次性）。
只呼叫已凍結的 production 函式（core.data／metrics／score／select），不設計任何新指標、評分或判斷；rescue 用 rescue_rule.py（獨立實作，不改 core）。
順序：① 一次性守門 → ② freeze manifest 不可變 → ③ integrity gate（在取得任何價格之前）→ ④ rescue 交叉檢驗（83 檔開發集，仍無價格）
      → ⑤ 依凍結順序抓資料（900 根充足性、依凍結 FALLBACK 替補；抓取失敗＝BLOCKED，不替補）→ ⑥ 對「全部 100 檔」執行 production ＋ rescue
      → ⑦ commit 前檢查 → ⑧ 才寫出 raw outputs（commit A），之後才 --finalize 產生 trigger summary（commit B）。
本程式在 commit A 之前只印 ticker、bar 數、日期、是否足夠；不印任何 candidate／final／分數／報酬／trigger。
用法（GitHub Actions）：python experiments/rescue_validation/run_validation.py
                        python experiments/rescue_validation/run_validation.py --finalize --raw-commit SHA"""
import argparse, hashlib, inspect, json, os, platform, re, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE)]
import rescue_rule as RR
BATCH = 'STRUCTURAL_RESCUE_FRESH_VALIDATION_100'
FREEZE_COMMIT = '01d959d2adb62c9582952bb6446a093c67656a7c'          # 建立 freeze manifest 的 commit（pre-registration evidence）
MANIFEST_FILES = ['experiments/rescue_validation/freeze_manifest.json', 'experiments/rescue_validation/freeze_manifest.md']
HOLDOUT_MANIFEST_FILES = ['experiments/holdout_v22/freeze_manifest.json', 'experiments/holdout_v22/freeze_manifest.md']
N_TARGET, MIN_BARS = 100, 900
DEV_CSV = 'experiments/sar_confidence/sar_confidence_per_ticker.csv'
PER_TICKER_FILES = ['bars.csv', 'metrics.csv', 'scores.csv', 'smoothed_structural_scores.csv', 'selection.json', 'meta.json', 'rescue.json']
FORBIDDEN_WORDS = ['human', 'review', 'ground_truth', 'coverage', 'large_miss']                      # 輸出中不得出現的人工判斷欄位
NO_CHANGE_PATHS = ['core', 'data', 'research', 'app.py', 'README.md', 'experiments/holdout_v22', 'experiments/final_rules', 'experiments/sar_confidence', 'experiments/rescue_validation/freeze_manifest.json', 'experiments/rescue_validation/freeze_manifest.md']

class FetchError(RuntimeError): pass
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def sha256_file(p): return sha256_bytes(Path(p).read_bytes())
def utcnow(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def git(args, root): return subprocess.run(['git'] + args, cwd=root, capture_output=True)

def clean(o):
    import numpy as np
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o); return None if f != f or f in (float('inf'), float('-inf')) else f
    if isinstance(o, np.bool_): return bool(o)
    return o

def write_blocked(out_dir, status, details, price_accessed):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    rec = dict(batch=BATCH, status=status, details=details, PRICE_DATA_ACCESSED=price_accessed, RESULTS_GENERATED=False, PRODUCTION_CHANGED=False, time_utc=utcnow())
    (Path(out_dir) / 'execution_blocked.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'); return rec

def verify_manifest_immutable(root):
    """freeze manifest（rescue 與 holdout）必須與 freeze commit 當時逐位元組相同；freeze commit 不在歷史中則回傳 None"""
    if git(['cat-file', '-e', FREEZE_COMMIT + '^{commit}'], root).returncode != 0: return None, 'freeze commit 不在此 clone 的歷史中，無法驗證'
    bad = []
    for f in MANIFEST_FILES + HOLDOUT_MANIFEST_FILES:
        blob = git(['show', f'{FREEZE_COMMIT}:{f}'], root)
        if blob.returncode != 0 or sha256_bytes(blob.stdout) != sha256_file(root / f): bad.append(f)
    return (not bad), bad

def integrity_gate(manifest, root, check_ranking=True):
    """所有 frozen identifier；回傳 (ok, 不一致清單, 檔案 hash, tree_ok)。呼叫端必須在抓價格之前停止。"""
    bad = []; want = manifest['production']['file_sha256_at_production_commit']; got = {}
    for f, h in want.items():
        p = root / f; got[f] = sha256_file(p) if p.exists() else None
        if got[f] != h: bad.append(f)
    if got.get('data/reference.parquet') != manifest['reference']['sha256'] and 'data/reference.parquet' not in bad: bad.append('data/reference.parquet')
    tree = git(['rev-parse', manifest['production']['commit'] + '^{tree}'], root); tree_ok = None if tree.returncode != 0 else tree.stdout.decode().strip() == manifest['production']['tree']
    if tree_ok is False: bad.append('production tree')
    if manifest.get('asof') != '2026-09-29': bad.append('ASOF')
    if check_ranking:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location('freeze_rv', HERE / 'freeze_rescue_validation.py'); F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)
            if sha256_file(F.SH.RAW) != manifest['source']['saved_raw_file_sha256']: bad.append('source S&P metadata SHA')
            if F.SH.SEED != manifest['ranking']['hash_seed']: bad.append('seed')
            _, _, _, _, ranked, _ = F.SH.build()
            val = [dict(rank=r['rank'], ticker=r['ticker'], sha256=r['sha256']) for r in ranked[F.RANK_LO - 1:F.RANK_HI]]; fb = [dict(rank=r['rank'], ticker=r['ticker'], sha256=r['sha256']) for r in ranked[F.FALLBACK_LO - 1:F.FALLBACK_HI]]
            if val != manifest['VALIDATION_TICKERS']: bad.append('rank 31–130 ordered list')
            if fb != manifest['FALLBACK_ORDER']: bad.append('fallback rank 131–150 ordered list')
            for f, h in manifest['diagnostic_evidence']['files_sha256'].items():
                if sha256_file(root / f) != h: bad.append(f)
        except Exception as e: bad.append(f'ranking recompute error: {type(e).__name__}: {e}')
    return not bad, bad, got, tree_ok

def dev_crosscheck(root):
    """rescue 獨立實作 vs sar_confidence_experiment::pick_posthoc，在既有 83 檔開發集候選上：輸出必須 83/83 相同，且 rescue final 與 CURRENT Rule B final 相同（changed=0）。不取得任何價格。"""
    import pandas as pd
    sys.path.insert(0, str(root / 'experiments' / 'sar_confidence')); import sar_confidence_experiment as X
    T = pd.read_csv(root / DEV_CSV, keep_default_na=False); pat = re.compile(r'(\d+)\(s(-?[\d.]+),r([+-][\d.]+)%,n(\d+)\)'); mism, changed = [], []
    for _, r in T.iterrows():
        c = [dict(period=int(a), s=float(b), r=float(d) / 100, n=int(e)) for a, b, d, e in pat.findall(r.candidates)]
        res = RR.evaluate(c)
        if len(c) != int(r.n_candidates) or res['rescue_final'] != X.pick_posthoc(c) or res['current_final'] != X.pick_rule_b(c) or res['current_final'] != int(r.CURRENT_RULE_B_final): mism.append(r.ticker)
        if res['rescue_final'] != res['current_final']: changed.append(r.ticker)
    return dict(n=len(T), identical=len(T) - len(mism), mismatched=mism, changed_finals=changed, ok=(len(T) == 83 and not mism and not changed))

def real_fetcher(tk):
    from core import data
    err = None
    for k in range(5):
        try: r = data.fetch_yahoo(tk); time.sleep(0.5); return r          # production 現有的資料抓取路徑（每檔間隔 0.5 秒避免被限流）
        except Exception as e: err = e; time.sleep(3 * (k + 1))
    raise FetchError(f'{tk}: {type(err).__name__}: {str(err)[:200]}')

def run(asof, out_dir, manifest_path, root, fetcher, real=True, log=print, n_target=N_TARGET, dev_check=True):
    """回傳 (exit_code, status)。out_dir 只在所有檢查通過後才寫入 raw outputs。"""
    out_dir = Path(out_dir); root = Path(root); t0 = utcnow()
    # ① 一次性守門
    if real and ((out_dir / 'execution_record.json').exists() or (out_dir / 'raw_outputs').exists()):
        log('ALREADY_OPENED：已有 execution record／raw outputs，拒絕重複開封（blocked 紀錄不算）。'); return 0, 'ALREADY_OPENED'
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    assert manifest['batch'] == BATCH and manifest['PRICE_DATA_ACCESSED'] is False and manifest['RESULTS_GENERATED'] is False, 'manifest 不是 pre-open 狀態'
    # ② freeze manifest 不可變
    man_ok, info = verify_manifest_immutable(root)
    if man_ok is False or (man_ok is None and real): write_blocked(out_dir, 'BLOCKED_INTEGRITY_DRIFT', {'freeze_manifest_changed_or_unverifiable': info}, False); log('BLOCKED_INTEGRITY_DRIFT：' + str(info)); return 2, 'BLOCKED_INTEGRITY_DRIFT'
    # ③ integrity gate（此時尚未取得任何價格資料）
    ok, bad, got, tree_ok = integrity_gate(manifest, root, check_ranking=real)
    if not ok: write_blocked(out_dir, 'BLOCKED_INTEGRITY_DRIFT', {'mismatched': bad}, False); log('BLOCKED_INTEGRITY_DRIFT：' + str(bad)); return 3, 'BLOCKED_INTEGRITY_DRIFT'
    log(f'PRODUCTION INTEGRITY：OK（{len(got)} 個檔案 hash、reference、tree {"OK" if tree_ok else "未驗證"}、來源 SHA、rank 31–130 與 131–150、ASOF 皆與 manifest 一致）')
    assert asof == manifest['asof'] == '2026-09-29'
    # ④ rescue 交叉檢驗（83 檔開發集；仍無價格）
    cc = dev_crosscheck(root) if dev_check else dict(n=0, identical=0, mismatched=[], changed_finals=[], ok=True, skipped=True)
    if not cc['ok']: write_blocked(out_dir, 'BLOCKED_RESCUE_IMPLEMENTATION_MISMATCH', {'crosscheck': cc}, False); log('BLOCKED_RESCUE_IMPLEMENTATION_MISMATCH：' + str(cc['mismatched'] + cc['changed_finals'])); return 4, 'BLOCKED_RESCUE_IMPLEMENTATION_MISMATCH'
    log(f"RESCUE CROSS-CHECK：{cc['identical']}/{cc['n']} 相同；開發集 finals changed = {len(cc['changed_finals'])}")
    sys.path.insert(0, str(root))
    import numpy as np, pandas as pd
    from core import data, metrics, score, select as sel
    assert sel.GAP == manifest['production']['frozen_parameters']['candidate_gap_default'] == 15 and [r[:4] for r in sel.RANGES][0] == ('短期', 15, 33, 252), 'production 參數與 manifest 不符'
    assert RR.STRUCT_POINTS == 10.0 and RR.SAR_PP == 0.10 and RR.GATE_PP == 0.05 and '+ 10.0 points' in manifest['STRUCTURAL_RESCUE_10PT_10PP']['conditions'][1] and '10 percentage points' in manifest['STRUCTURAL_RESCUE_10PT_10PP']['conditions'][2]
    primary, fallback = [x['ticker'] for x in manifest['VALIDATION_TICKERS']][:n_target], [x['ticker'] for x in manifest['FALLBACK_ORDER']]
    prank = {x['ticker']: x['rank'] for x in manifest['VALIDATION_TICKERS'] + manifest['FALLBACK_ORDER']}
    attempts, accepted, chain, mapping, pool = [], [], {}, {}, {}; fb_i = 0
    def evaluate(tk, role):
        raw = fetcher(tk); df = data.normalize(raw, asof)                                # 只保留 ≤ ASOF 的已完成日線
        if not len(df): raise FetchError(f'{tk}: EMPTY_AFTER_NORMALIZE（無法可靠判定資料量）')
        rec = dict(ticker=tk, role=role, rank=prank[tk], fetched_rows_total=int(len(raw)), bars_after_asof_dropped=int(len(raw) - len(df)), n_bars=int(len(df)),
                   first_date=str(df.date.iloc[0].date()), last_date=str(df.date.iloc[-1].date()), sufficient=bool(len(df) >= MIN_BARS))
        assert df.date.iloc[-1] <= pd.Timestamp(asof), 'cutoff 失敗'
        attempts.append(rec); pool[tk] = df; log(f"DATA {tk}: bars={rec['n_bars']} first={rec['first_date']} last={rec['last_date']} sufficient={rec['sufficient']}"); return rec
    # ⑤ 抓資料與替補（順序完全依 manifest；資料不足不算失敗；抓取失敗＝BLOCKED，不替補）
    try:
        for tk in primary:
            rec = evaluate(tk, 'PRIMARY')
            if rec['sufficient']: accepted.append(tk); mapping[tk] = tk; continue
            chain[tk] = []
            while True:
                if fb_i >= len(fallback): write_blocked(out_dir, 'BLOCKED_INSUFFICIENT_FALLBACK_POOL', {'primary': tk, 'accepted_so_far': len(accepted)}, True); log('BLOCKED_INSUFFICIENT_FALLBACK_POOL'); return 6, 'BLOCKED_INSUFFICIENT_FALLBACK_POOL'
                fb = fallback[fb_i]; fb_i += 1; r2 = evaluate(fb, 'FALLBACK'); chain[tk].append(dict(ticker=fb, rank=prank[fb], n_bars=r2['n_bars'], sufficient=r2['sufficient']))
                if r2['sufficient']: accepted.append(fb); mapping[tk] = fb; break
    except FetchError as e:
        write_blocked(out_dir, 'BLOCKED_FETCH_ERROR', {'message': str(e)}, True); log('BLOCKED_FETCH_ERROR：' + str(e)); return 5, 'BLOCKED_FETCH_ERROR'
    if len(accepted) != n_target: write_blocked(out_dir, 'BLOCKED_INSUFFICIENT_FALLBACK_POOL', {'n': len(accepted)}, True); return 6, 'BLOCKED_INSUFFICIENT_FALLBACK_POOL'
    # ⑥ 對全部檔案執行 production ＋ rescue（不顯示任何結果）
    ref = pd.read_parquet(root / 'data' / 'reference.parquet'); staged = {}
    try:
        for tk in accepted:
            df = pool[tk]; M = metrics.compute_metrics(df); S = score.score_table(M, ref); R = sel.select(df, S); P_, Ss = sel.smoothed_scores(S); sm = dict(zip(P_, Ss)); short = R['短期']
            cands = [dict(period=c['均線'], s=float(c['結構分']), r=float(c['反手報酬']), n=int(c['反手筆數'])) for c in short['cands']]
            assert all(c['s'] == float(sm[c['period']]) for c in cands), 'candidate 結構分與 smoothed score 不一致'
            ev = RR.evaluate(cands); assert ev['current_final'] == short['final'], 'CURRENT Rule B 與 production final 不一致'
            staged[tk] = dict(df=df, M=M, S=S, R=R, smooth=pd.DataFrame({'period': P_, 'smoothed_structural_score': Ss}), suit=sel.suitability(S), cands=short['cands'], ev=ev)
            log(f'PRODUCTION RUN {tk}: done')
    except Exception as e:
        write_blocked(out_dir, 'BLOCKED_PRODUCTION_ERROR', {'ticker': tk, 'error_type': type(e).__name__, 'message': str(e)[:200]}, True); log(f'BLOCKED_PRODUCTION_ERROR {tk} {type(e).__name__}'); return 7, 'BLOCKED_PRODUCTION_ERROR'
    # ⑦ 寫到暫存區並做 commit 前檢查
    tmp = Path(tempfile.mkdtemp(prefix='rescue_stage_')); raw_dir = tmp / 'raw_outputs'; index = {}; req_of = {v: k for k, v in mapping.items()}
    defaults = {k: (None if v.default is inspect._empty else v.default) for k, v in inspect.signature(sel.select).parameters.items() if k not in ('df', 'S')}
    for tk, x in staged.items():
        d = raw_dir / tk; d.mkdir(parents=True); rec = next(a for a in attempts if a['ticker'] == tk); ev = x['ev']
        x['df'].drop(columns='date').to_csv(d / 'bars.csv', index=False); x['M'].to_csv(d / 'metrics.csv', index=False); x['S'].to_csv(d / 'scores.csv', index=False); x['smooth'].to_csv(d / 'smoothed_structural_scores.csv', index=False)
        (d / 'selection.json').write_text(json.dumps(dict(ticker=tk, asof=asof, production_select_defaults_used=clean(defaults), selection=clean(x['R']), suitability_short_long=clean(x['suit'])), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (d / 'meta.json').write_text(json.dumps(dict(ticker=tk, role=rec['role'], asof=asof, n_bars=rec['n_bars'], first_date=rec['first_date'], last_date=rec['last_date'], bars_sha256=sha256_file(d / 'bars.csv'),
                                                     price_source='core.data.fetch_yahoo (production path), range=5y, cut at ASOF'), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        rp = req_of[tk]; is_fb = (rp != tk)
        rescue = dict(requested_primary_ticker=rp, actual_ticker=tk, primary_rank=prank[rp], replacement_rank=prank[tk] if is_fb else None, bar_count=rec['n_bars'], first_date=rec['first_date'], last_date=rec['last_date'], asof=asof,
                      short_candidates=[dict(period=c['均線'], structural_score_unrounded=c['結構分'], score_displayed_rounded=c['分數'], sar_return=c['反手報酬'], sar_trades=c['反手筆數']) for c in x['cands']],
                      current_finalists=ev['current_finalists'], current_final=ev['current_final'], structural_best_period=ev['structural_best_period'], structural_best_score=ev['structural_best_score'],
                      observed_best_sar=ev['observed_best_sar'], structural_score_advantage=ev['structural_score_advantage'], sar_gap=ev['sar_gap'], C1=ev['C1'], C2=ev['C2'], C3=ev['C3'], trigger=ev['trigger'], rescue_final=ev['rescue_final'])
        (d / 'rescue.json').write_text(json.dumps(clean(rescue), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index[tk] = {f: sha256_file(d / f) for f in PER_TICKER_FILES}
    (raw_dir / 'index.json').write_text(json.dumps(index, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    _, _, got2, _ = integrity_gate(manifest, root, check_ranking=False); man_ok2, _ = verify_manifest_immutable(root)
    dirty = git(['status', '--porcelain', '--'] + NO_CHANGE_PATHS, root).stdout.decode().strip()
    text_blob = ''.join((raw_dir / tk / f).read_text(encoding='utf-8').lower() for tk in accepted for f in ('selection.json', 'meta.json', 'rescue.json'))
    checks = {'exactly_n_actual_stocks': len(accepted) == n_target and len(set(accepted)) == n_target,
              'each_stock_ge_900_bars': all(next(a for a in attempts if a['ticker'] == tk)['n_bars'] >= MIN_BARS for tk in accepted),
              'last_date_le_asof': all(next(a for a in attempts if a['ticker'] == tk)['last_date'] <= asof for tk in accepted),
              'production_hashes_and_reference_still_match_freeze_manifest': got2 == got and all(got2[f] == h for f, h in manifest['production']['file_sha256_at_production_commit'].items()),
              'freeze_manifests_byte_identical_to_freeze_commit': (man_ok2 is True) or (not real),
              'short_selector_completed_all': all(len(staged[tk]['cands']) >= 1 and 'final' in staged[tk]['R']['短期'] for tk in accepted),
              'rescue_crosscheck_83_of_83': cc['ok'],
              'no_manual_review_fields': not any(w in text_blob for w in FORBIDDEN_WORDS),
              'no_threshold_adjustment': RR.STRUCT_POINTS == 10.0 and RR.SAR_PP == 0.10,
              'raw_outputs_all_serialized': all((raw_dir / tk / f).exists() and (raw_dir / tk / f).stat().st_size > 0 for tk in accepted for f in PER_TICKER_FILES),
              'no_production_or_frozen_file_change_in_worktree': dirty == ''}
    if not all(checks.values()):
        write_blocked(out_dir, 'BLOCKED_PRE_COMMIT_CHECK_FAILED', {'failed_checks': [k for k, v in checks.items() if not v]}, True); log('BLOCKED_PRE_COMMIT_CHECK_FAILED：' + str([k for k, v in checks.items() if not v])); return 8, 'BLOCKED_PRE_COMMIT_CHECK_FAILED'
    # ⑧ 全部通過才寫入 repo 目錄（commit A 的內容；此刻沒有任何人檢視結果）
    import shutil; out_dir.mkdir(parents=True, exist_ok=True); shutil.copytree(raw_dir, out_dir / 'raw_outputs')
    record = dict(batch=BATCH, status='RAW_OUTPUTS_WRITTEN_PENDING_COMMIT', raw_output_commit_sha=None,
                  production=dict(commit=manifest['production']['commit'], tree=manifest['production']['tree'], hashes_verified=True, tree_verified=tree_ok, file_sha256_verified=got2), reference_sha256=got2['data/reference.parquet'], asof=asof,
                  PRICE_DATA_ACCESSED=True, RESULTS_GENERATED=True,
                  freeze_manifest=dict(freeze_commit=FREEZE_COMMIT, unchanged_since_freeze_commit=man_ok2, sha256={f: sha256_file(root / f) for f in MANIFEST_FILES + HOLDOUT_MANIFEST_FILES}),
                  rescue_crosscheck_83={k: v for k, v in cc.items()}, primary_requested=primary, fallback_order_frozen=fallback,
                  data_sufficiency=attempts, replacements=[dict(replaced_primary=p, chain=c, final_replacement=mapping[p]) for p, c in chain.items()], mapping_primary_to_actual=mapping,
                  actual_tickers=accepted, actual_validation_n=len(accepted), min_bars_required=MIN_BARS, pre_commit_checks=checks,
                  raw_output_dir='experiments/rescue_validation/raw_outputs', raw_outputs_index_sha256=sha256_file(out_dir / 'raw_outputs' / 'index.json'),
                  audit_notes=['bars.csv／metrics.csv／scores.csv 以 Python repr 寫出；重讀請用 pd.read_csv(..., float_precision="round_trip")。',
                               'selection.json 是 core.select.select(df, score_table(compute_metrics(df), reference)) 的原樣輸出；rescue.json 是 rescue_rule.evaluate 對短期候選的輸出。'],
                  no_review_note='原始輸出在使用者看到任何 trigger case 之前產生並先 commit；本檔（commit A）不含任何 candidate／final／分數／報酬／trigger。',
                  environment=dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__, github_run_id=os.environ.get('GITHUB_RUN_ID'), github_sha=os.environ.get('GITHUB_SHA')), started_utc=t0, finished_utc=utcnow())
    (out_dir / 'execution_record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    log(f'ALL {n_target} RAW OUTPUTS WRITTEN；等待 commit A（在 commit 之前不檢視任何結果）'); return 0, 'RAW_OUTPUTS_WRITTEN_PENDING_COMMIT'

def finalize(out_dir, raw_commit, root=ROOT, log=print, check_git=True):
    """commit A 之後才可呼叫：讀取 raw outputs 產生 aggregate trigger summary、更新 execution record（commit B）。不做 PASS/FAIL 判斷。"""
    out_dir = Path(out_dir); rec_p = out_dir / 'execution_record.json'; rec = json.loads(rec_p.read_text(encoding='utf-8'))
    assert rec['status'] == 'RAW_OUTPUTS_WRITTEN_PENDING_COMMIT', '只有 commit A 之前的 execution record 可以 finalize'
    if check_git:
        assert git(['cat-file', '-e', raw_commit + '^{commit}'], root).returncode == 0, 'raw output commit 不存在'
        assert git(['diff', '--quiet', raw_commit, '--', 'experiments/rescue_validation/raw_outputs'], root).returncode == 0, 'raw_outputs 與 commit A 不一致'
    assert sha256_file(out_dir / 'raw_outputs' / 'index.json') == rec['raw_outputs_index_sha256']
    rows = [json.loads((out_dir / 'raw_outputs' / tk / 'rescue.json').read_text(encoding='utf-8')) for tk in rec['actual_tickers']]
    trig = [r for r in rows if r['trigger']]
    for r in rows: assert r['trigger'] == (r['rescue_final'] != r['current_final']) == (r['C1'] and r['C2'] and r['C3'])
    status = 'INSUFFICIENT_VALIDATION' if not trig else 'MANUAL_REVIEW_REQUIRED'
    summ = dict(batch=BATCH, raw_output_commit_sha=raw_commit, actual_validation_n=len(rows), trigger_count=len(trig), trigger_tickers=[r['actual_ticker'] for r in trig], VALIDATION_STATUS=status,
                triggers=[dict(ticker=r['actual_ticker'], current_final=r['current_final'], rescue_final=r['rescue_final'], structural_score_advantage=r['structural_score_advantage'], sar_gap=r['sar_gap'], C1=r['C1'], C2=r['C2'], C3=r['C3']) for r in trig],
                note='本檔只產生結果，不判 PASS/FAIL。trigger=0 → INSUFFICIENT_VALIDATION（不是 PASS）；trigger≥1 → 全部 trigger case 都需人工 review（不抽樣）。10.0／10pp 不得調整。')
    (out_dir / 'trigger_summary.json').write_text(json.dumps(clean(summ), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    L = [f'# {BATCH} — trigger summary（不判 PASS/FAIL）\n', f'- raw output commit（commit A）：`{raw_commit}`', f"- actual validation N：{len(rows)}", f'- trigger count：**{len(trig)} / {len(rows)}**', f'- VALIDATION_STATUS：**{status}**\n']
    if trig:
        L += ['| ticker | CURRENT final | rescue final | structural score advantage | SAR gap | C1 | C2 | C3 |', '|---|---|---|---|---|---|---|---|']
        L += [f"| {r['actual_ticker']} | {r['current_final']} | {r['rescue_final']} | {r['structural_score_advantage']:.4f} | {r['sar_gap']*100:.2f}pp | {r['C1']} | {r['C2']} | {r['C3']} |" for r in trig]
    (out_dir / 'trigger_summary.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    rec.update(status='RAW_OUTPUTS_COMMITTED_BEFORE_EXPOSURE', raw_output_commit_sha=raw_commit, trigger_count=len(trig), trigger_tickers=summ['trigger_tickers'], VALIDATION_STATUS=status, trigger_summary_file='experiments/rescue_validation/trigger_summary.json')
    rec_p.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'); log(f'FINALIZED：trigger {len(trig)} / {len(rows)}；{status}'); return summ

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-29'); ap.add_argument('--finalize', action='store_true'); ap.add_argument('--raw-commit'); a = ap.parse_args()
    if a.finalize: finalize(HERE, a.raw_commit); return
    code, status = run(a.asof, HERE, HERE / 'freeze_manifest.json', ROOT, real_fetcher, real=True); print('STATUS:', status); sys.exit(code)

if __name__ == '__main__': main()
