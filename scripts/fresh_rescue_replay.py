"""Fresh 100 replay：用 commit A 已封存的 bars.csv（不抓 Yahoo）重跑目前 production selector，與封存時（規則 B、尚無 rescue）的 selection.json 逐欄比較。
要求：只有 PG 短期 22→25、FDX 短期 18→21 改變；其餘 98 檔的短期與全部 100 檔的中期／長期 final、候選完全相同。否則 STOP — RESCUE_REPLAY_MISMATCH。
兩種比較：(A) 同一個 process、同一份分數表，目前 select vs 改動前的 select（git PREV_COMMIT 的 core/select.py）——逐位元組相同（除了 rescue）；
(B) vs 封存的 selection.json——final／候選週期／筆數完全相同，浮點欄位容許 1e-9（中期分數的加總順序受 PYTHONHASHSEED 影響：core/score.py 以 set 迭代組中期權重，屬既有行為、與本改動無關）。
用法：python scripts/fresh_rescue_replay.py [--out experiments/production_rescue]"""
import argparse, hashlib, io, json, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
RAW_COMMIT = '07023d68ffb56588e978f2bc65af063966d10067'
RAW = ROOT / 'experiments' / 'rescue_validation' / 'raw_outputs'
EXPECT = {'PG': (22, 25), 'FDX': (18, 21)}
PREV_COMMIT = '85b77549d2d785a649fb6f492a4a094b523595a6'          # 改動前（規則 B、尚無 rescue）的 production
FTOL = 1e-9

def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o); return None if f != f or f in (float('inf'), float('-inf')) else f
    if isinstance(o, np.bool_): return bool(o)
    return o

def prev_select():
    import importlib.util, types
    src = subprocess.run(['git', 'show', f'{PREV_COMMIT}:core/select.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType('core._select_prev'); m.__package__ = 'core'; exec(compile(src, 'core/select.py@prev', 'exec'), m.__dict__); return m

def close(a, b):
    if isinstance(a, dict): return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
    if isinstance(a, list): return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float): return abs(a - b) <= FTOL * max(1., abs(a))
    return a == b and type(a) == type(b)

def one(tk):
    from core import data, metrics, score, select as sel
    rel = f'experiments/rescue_validation/raw_outputs/{tk}/bars.csv'
    blob = subprocess.run(['git', 'show', f'{RAW_COMMIT}:{rel}'], cwd=ROOT, capture_output=True, check=True).stdout
    assert hashlib.sha256(blob).digest() == hashlib.sha256((ROOT / rel).read_bytes()).digest(), f'{tk} bars.csv 與 commit A 不同'
    meta = json.loads((RAW / tk / 'meta.json').read_text(encoding='utf-8'))
    df = data.normalize(pd.read_csv(io.BytesIO(blob), float_precision='round_trip'), meta['asof'])
    ref = pd.read_parquet(ROOT / 'data' / 'reference.parquet')
    S = score.score_table(metrics.compute_metrics(df), ref); R = sel.select(df, S); R0 = prev_select().select(df, S)
    return tk, (clean(R), clean(R0))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default='experiments/production_rescue'); a = ap.parse_args(); out = (ROOT / a.out) if not Path(a.out).is_absolute() else Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rec = json.loads((ROOT / 'experiments/rescue_validation/execution_record.json').read_text(encoding='utf-8')); tks = rec['actual_tickers']; assert len(tks) == 100
    with ProcessPoolExecutor(4) as ex: new = dict(ex.map(one, tks))
    rows, bad = [], []
    for tk in tks:
        old = json.loads((RAW / tk / 'selection.json').read_text(encoding='utf-8'))['selection']; nw, prv = new[tk]
        for nm in ('短期', '中期', '長期'):
            same_prev = prv[nm]['cands'] == nw[nm]['cands'] and prv[nm]['best'] == nw[nm]['best']                   # (A) 逐位元組
            same_seal = close(old[nm]['cands'], nw[nm]['cands']) and close(old[nm]['best'], nw[nm]['best']) and [c['均線'] for c in old[nm]['cands']] == [c['均線'] for c in nw[nm]['cands']]   # (B)
            exact_seal = old[nm]['cands'] == nw[nm]['cands']
            of, pf, nf = old[nm]['final'], prv[nm]['final'], nw[nm]['final']
            rows.append(dict(ticker=tk, range=nm, sealed_final=of, prev_select_final=pf, replay_final=nf, changed=of != nf, candidates_identical_vs_prev_select=same_prev,
                             candidates_match_sealed_tol=same_seal, candidates_bit_identical_sealed=exact_seal))
            exp_change = nm == '短期' and tk in EXPECT
            if not same_prev or not same_seal or of != pf or (exp_change and (of, nf) != EXPECT[tk]) or (not exp_change and of != nf): bad.append(f'{tk} {nm}: sealed {of} / prev {pf} → replay {nf}（候選 vs prev：{same_prev}；vs 封存：{same_seal}）')
    T = pd.DataFrame(rows); T.to_csv(out / 'fresh100_replay.csv', index=False); ch = T[T.changed]
    status = 'PASS' if not bad else 'STOP — RESCUE_REPLAY_MISMATCH'
    L = [f'# Fresh 100 replay（commit A 封存的 bars；目前 production selector vs 封存時的規則 B 輸出）\n', f'- raw output commit：`{RAW_COMMIT}`（bars.csv 逐檔與 commit A blob 比對）', f'- reference：`data/reference.parquet`（未重建）',
         f'- (A) 同 process、同分數表：目前 select vs 改動前 select（`{PREV_COMMIT[:7]}`）候選與 best 逐位元組相同：{"是" if T.candidates_identical_vs_prev_select.all() else "**否**"}（{int(T.candidates_identical_vs_prev_select.sum())}/{len(T)}）',
         f'- (B) vs 封存 selection.json：final 與候選週期完全相同、浮點 ≤{FTOL:g}：{"是" if T.candidates_match_sealed_tol.all() else "**否**"}（{int(T.candidates_match_sealed_tol.sum())}/{len(T)}）；逐位元組相同 {int(T.candidates_bit_identical_sealed.sum())}/{len(T)}'
         + f'；不逐位元組相同者：中期 {int((~T.candidates_bit_identical_sealed & (T.range == "中期")).sum())}、短期 {int((~T.candidates_bit_identical_sealed & (T.range == "短期")).sum())}、長期 {int((~T.candidates_bit_identical_sealed & (T.range == "長期")).sum())}'
         + '——原因：core/score.py 以 set 迭代組中期權重，加總順序受 PYTHONHASHSEED 影響（既有行為，與本改動無關；短期只出現在 SMA33，因平滑會用到 SMA34 的中期分數），差異只在最後一位',
         f'- 預期：只有 PG 短期 22→25、FDX 短期 18→21', f'- 短期其餘 {len(tks) - len(EXPECT)} 檔 final 不變：{"是" if not any(b for b in bad if "短期" in b) else "否"}；中期／長期 100 檔 final 不變：{"是" if not ch[ch.range != "短期"].shape[0] else "否"}',
         f'\n**STATUS：{status}**'] + ([f'- {b}' for b in bad] if bad else [])
    (out / 'fresh100_replay.md').write_text('\n'.join(L) + '\n', encoding='utf-8'); print('\n'.join(L)); sys.exit(0 if not bad else 9)

if __name__ == '__main__': main()
