"""SUITABILITY_VALIDATION_30 的一次性開封：依凍結的 freeze manifest 選出 30 檔、產生審閱圖；分數與分層封存在 sealed_scores.json（審閱完成前不得給使用者看）。
順序：① 一次性守門 → ② freeze manifest 與 freeze commit 逐位元組相同 → ③ production 檔案未變、reference 讀 freeze commit 的 blob（比對 SHA）
      → ④ 依排名逐檔：抓資料（失敗／不足 900 根→略過並記錄）→ 算短期適合度 → 依凍結 Q1／Q3 分層 → 各層取前 10 檔 → ⑤ 畫圖（只標 ticker＋SMA）
      → ⑥ commit 前檢查 → ⑦ 寫出（commit A）。log 只印 ticker 與資料狀態，不印分數、分層。
用法（GitHub Actions）：python experiments/suitability_validation/open_validation.py"""
import argparse, hashlib, io, json, os, platform, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
BATCH = 'SUITABILITY_VALIDATION_30'
FREEZE_COMMIT = '63d88f16bd0229eb56344339f25900a4c6d01bcc'
MANIFEST_FILES = ['experiments/suitability_validation/freeze_manifest.json', 'experiments/suitability_validation/freeze_manifest.md']
BLIND_WORDS = ['適合度', 'suitab', 'stratum', 'strata', 'LOW', 'MID', 'HIGH', 'Q1', 'Q3', '分數']
class FetchError(RuntimeError): pass
SHA = lambda b: hashlib.sha256(b).hexdigest()
def sha_file(p): return SHA(Path(p).read_bytes())
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

def blocked(out, status, details, price):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'execution_blocked.json').write_text(json.dumps(dict(batch=BATCH, status=status, details=details, PRICE_DATA_ACCESSED=price, RESULTS_GENERATED=False, time_utc=utcnow()), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return status

def stratum(x, q1, q3): return 'LOW' if x <= q1 else ('HIGH' if x >= q3 else 'MID')

def real_fetcher(tk):
    from core import data
    err = None
    for k in range(4):
        try: r = data.fetch_yahoo(tk); time.sleep(0.4); return r
        except Exception as e: err = e; time.sleep(3 * (k + 1))
    raise FetchError(f'{tk}: {type(err).__name__}: {str(err)[:160]}')

def run(out, root, fetcher, manifest_path, freeze_commit=FREEZE_COMMIT, real=True, log=print, ref_bytes=None):
    out = Path(out); root = Path(root); t0 = utcnow()
    if real and ((out / 'execution_record.json').exists() or (out / 'review_bundle').exists()):
        log('ALREADY_OPENED'); return 'ALREADY_OPENED'
    m = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    assert m['batch'] == BATCH and m['PRICE_DATA_ACCESSED'] is False and m['RESULTS_GENERATED'] is False
    # ② freeze manifest 不可變
    if real:
        bad = [f for f in MANIFEST_FILES if git(['show', f'{freeze_commit}:{f}'], root).returncode != 0 or SHA(git(['show', f'{freeze_commit}:{f}'], root).stdout) != sha_file(root / f)]
        if bad: log('BLOCKED_FREEZE_MANIFEST_CHANGED ' + str(bad)); return blocked(out, 'BLOCKED_FREEZE_MANIFEST_CHANGED', bad, False)
    # ③ production 未變；reference 用 freeze commit 的 blob
    drift = [f for f, h in m['production']['file_sha256'].items() if f != 'data/reference.parquet' and sha_file(root / f) != h]
    if drift: log('BLOCKED_PRODUCTION_DRIFT ' + str(drift)); return blocked(out, 'BLOCKED_PRODUCTION_DRIFT', drift, False)
    if ref_bytes is None: ref_bytes = git(['show', f'{freeze_commit}:data/reference.parquet'], root).stdout
    if SHA(ref_bytes) != m['reference']['sha256']: log('BLOCKED_REFERENCE_MISMATCH'); return blocked(out, 'BLOCKED_REFERENCE_MISMATCH', SHA(ref_bytes), False)
    log('INTEGRITY OK（freeze manifest、production 檔案、凍結 reference 皆一致）')
    sys.path.insert(0, str(root))
    import numpy as np, pandas as pd
    from core import data, metrics, score, select as sel, charts
    ref = pd.read_parquet(io.BytesIO(ref_bytes)); q1, q3 = m['strata']['Q1'], m['strata']['Q3']; k_per = m['strata']['per_stratum']; asof = m['asof']; minb = m['min_bars']
    picked = {s: [] for s in ('LOW', 'MID', 'HIGH')}; screen, staged = [], {}
    for it in m['screening_pool']:
        if all(len(v) >= k_per for v in picked.values()): break
        tk = it['ticker']; rec = dict(rank=it['rank'], ticker=tk)
        try: raw = fetcher(tk)
        except FetchError as e: rec.update(status='SKIPPED_FETCH_FAILURE', reason=str(e)); screen.append(rec); log(f'DATA {tk}: fetch failure → skipped'); continue
        df = data.normalize(raw, asof); n = len(df); rec.update(bars=n, first=str(df.date.iloc[0].date()) if n else None, last=str(df.date.iloc[-1].date()) if n else None)
        if n < minb: rec.update(status='SKIPPED_INSUFFICIENT_BARS'); screen.append(rec); log(f'DATA {tk}: bars={n} → skipped'); continue
        assert df.date.iloc[-1] <= pd.Timestamp(asof)
        S = score.score_table(metrics.compute_metrics(df), ref); R = sel.select(df, S); suit_s, suit_l = sel.suitability(S); st = stratum(suit_s, q1, q3)
        rec.update(status='SCORED', short_suitability=suit_s, long_max=suit_l, stratum=st, short_final=int(R['短期']['final']))
        if len(picked[st]) < k_per: picked[st].append(tk); rec['selected'] = True; staged[tk] = dict(df=df, S=S, R=R, rec=rec)
        else: rec['selected'] = False
        screen.append(rec); log(f'DATA {tk}: bars={n} ok')
    if not all(len(v) >= k_per for v in picked.values()):
        log('BLOCKED_INSUFFICIENT_POOL'); return blocked(out, 'BLOCKED_INSUFFICIENT_POOL', {s: len(v) for s, v in picked.items()}, True)
    sel_tk = [t for v in picked.values() for t in v]; seed = 'MA_SELECTOR_SUITABILITY_REVIEW_ORDER_2026-10-29|'
    order = sorted(sel_tk, key=lambda t: SHA((seed + t).encode()))
    assert seed in m['review']['order']
    # ⑤ 寫到暫存區
    tmp = Path(tempfile.mkdtemp(prefix='suit_stage_')); rb = tmp / 'review_bundle'; rawd = tmp / 'raw_outputs'; rb.mkdir(); rawd.mkdir(); rows = []
    for i, tk in enumerate(order, 1):
        x = staged[tk]; p = x['rec']['short_final']; d = rawd / tk; d.mkdir()
        x['df'].drop(columns='date').to_csv(d / 'bars.csv', index=False); x['S'].to_csv(d / 'scores_table.csv', index=False)
        (d / 'selection.json').write_text(json.dumps(clean(x['R']), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        png = charts.chart_png(x['df'], p, f'{tk} SMA{p}'); name = f'{i:02d}_{tk}_SMA{p}.png'; (rb / name).write_bytes(png)
        rows.append(dict(order=i, ticker=tk, ma=f'SMA{p}', image=name, image_sha256=SHA(png), bars_sha256=sha_file(d / 'bars.csv'), bars=x['rec']['bars'], first=x['rec']['first'], last=x['rec']['last']))
    L = [f'# {BATCH} — review bundle（盲測：只有圖）\n', f'- 問題：{m["review"]["question_wording"]}', '- 評分：' + '／'.join(m['review']['rating_scale']), f'- 每張圖：production 短期最後選擇的 SMA；bars=126、segs=4（近兩年四段）；ASOF {asof}', '- 順序：freeze manifest 凍結的雜湊排序\n',
         '| # | ticker | 均線 | 圖檔 | 圖片 SHA-256 | 資料起訖 |', '|---|---|---|---|---|---|'] + [f"| {r['order']} | {r['ticker']} | {r['ma']} | `{r['image']}` | `{r['image_sha256']}` | {r['first']} ~ {r['last']} |" for r in rows]
    (rb / 'review_manifest.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    sealed = dict(batch=BATCH, note='審閱完成並 commit 全部評分之前，不得顯示給使用者。', Q1=q1, Q3=q3, selected={tk: dict(order=order.index(tk) + 1, stratum=staged[tk]['rec']['stratum'], short_suitability=staged[tk]['rec']['short_suitability'], long_max=staged[tk]['rec']['long_max'], short_final=staged[tk]['rec']['short_final']) for tk in sel_tk},
                  screening=screen)
    (tmp / 'sealed_scores.json').write_text(json.dumps(clean(sealed), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # ⑥ commit 前檢查
    blob = ''.join(f.read_text(encoding='utf-8') for f in rb.glob('*.md')) + ' '.join(f.name for f in rb.iterdir())
    for tk in sel_tk: blob = blob.replace(tk, '')                   # 代號本身（例如 MIDD）不算洩漏
    drift2 = [f for f, h in m['production']['file_sha256'].items() if f != 'data/reference.parquet' and sha_file(root / f) != h]
    checks = {'n_selected_equals_manifest': len(sel_tk) == m['strata']['n_total'] * k_per // 10 == 3 * k_per and len(set(sel_tk)) == len(sel_tk), 'ten_per_stratum': all(len(v) == k_per for v in picked.values()),
              'each_ge_min_bars': all(staged[t]['rec']['bars'] >= minb for t in sel_tk), 'last_le_asof': all(staged[t]['rec']['last'] <= asof for t in sel_tk),
              'production_unchanged': not drift2, 'review_bundle_blind': not any(w in blob for w in BLIND_WORDS), 'one_image_per_stock': len(list(rb.glob('*.png'))) == len(sel_tk)}
    if not all(checks.values()): log('BLOCKED_PRE_COMMIT_CHECK_FAILED ' + str([k for k, v in checks.items() if not v])); return blocked(out, 'BLOCKED_PRE_COMMIT_CHECK_FAILED', [k for k, v in checks.items() if not v], True)
    # ⑦ 寫入
    out.mkdir(parents=True, exist_ok=True); shutil.copytree(rb, out / 'review_bundle'); shutil.copytree(rawd, out / 'raw_outputs'); shutil.copy(tmp / 'sealed_scores.json', out / 'sealed_scores.json')
    rec = dict(batch=BATCH, status='OPENED_PENDING_COMMIT', raw_output_commit_sha=None, freeze_commit=freeze_commit, asof=asof, PRICE_DATA_ACCESSED=True, RESULTS_GENERATED=True,
               review_order=[dict(order=r['order'], ticker=r['ticker'], ma=r['ma']) for r in rows], n_screened=len(screen),
               data_status=[dict(rank=s['rank'], ticker=s['ticker'], status='FETCHED' if s['status'] == 'SCORED' else s['status'], bars=s.get('bars')) for s in screen],
               sealed_scores_sha256=sha_file(out / 'sealed_scores.json'), pre_commit_checks=checks, reference_sha256=SHA(ref_bytes),
               environment=dict(python=platform.python_version(), github_run_id=os.environ.get('GITHUB_RUN_ID')), started_utc=t0, finished_utc=utcnow(),
               note='本檔不含分數與分層；分數封存在 sealed_scores.json，全部評分 commit 前不得顯示。')
    (out / 'execution_record.json').write_text(json.dumps(clean(rec), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    log(f'OPENED：30 檔審閱圖已寫入（篩選 {len(screen)} 檔）'); return 'OPENED_PENDING_COMMIT'

def main():
    ap = argparse.ArgumentParser(); ap.parse_args()
    st = run(HERE, ROOT, real_fetcher, HERE / 'freeze_manifest.json'); print('STATUS:', st); sys.exit(0 if st in ('OPENED_PENDING_COMMIT', 'ALREADY_OPENED') else 2)

if __name__ == '__main__': main()
