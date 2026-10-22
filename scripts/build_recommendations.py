"""批次產生「建議均線」JSON（給 my-stock-screener 的 Atlas 圖表讀）：每檔一個 <ticker>.json＋index.json
流程與網頁預設完全相同（core/recommend.py）；不改任何規則。
用法：python scripts/build_recommendations.py --from-dir ../data --out ../docs/report/ma-selector [--workers 4] [--bars-dir 快取] [--limit 20]
  --from-dir：用目錄內 *.csv 的檔名當股票清單（略過 ^ 開頭的指數）；--tickers：直接列代號
  --bars-dir：從該目錄讀 <ticker>.csv（time/date,open,high,low,close,volume），沒有才抓 Yahoo 5 年日K
抓不到或資料不足的股票保留上一次的檔案；成功率 < --min-success（預設 50%）時不寫任何檔案並以錯誤結束。"""
import argparse, datetime as dt, json, os, re, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import data
from core.recommend import recommend, VERSION
ROOT = Path(__file__).resolve().parents[1]; SAFE = re.compile(r'^[A-Z0-9][A-Z0-9.\-]{0,31}$')
_REF = _META = _BARS = None

def _init(bars_dir):
    global _REF, _META, _BARS
    f = ROOT / 'data' / 'reference.parquet'; _REF = pd.read_parquet(f); _META = json.loads(f.with_suffix('.json').read_text()); _BARS = Path(bars_dir) if bars_dir else None

def _bars(tk):
    if _BARS and (_BARS / f'{tk}.csv').exists(): return data.load(_BARS / f'{tk}.csv')
    for i in range(3):
        try: return data.fetch_yahoo(tk)
        except Exception:
            if i == 2: raise
            time.sleep(2 * 2 ** i)

def work(tk):
    try:
        r = recommend(_bars(tk), _REF, tk, reference_asof=_META.get('asof'))
        return tk, r, None if r else '資料不足'
    except Exception as e: return tk, None, f'{type(e).__name__}: {e}'[:200]

def tickers_from(a):
    tks = list(a.tickers or [])
    if a.from_dir: tks += [p.stem for p in Path(a.from_dir).glob('*.csv')]
    tks = sorted({t.strip().upper() for t in tks if SAFE.match(t.strip().upper())})
    return tks[:a.limit] if a.limit else tks

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument('--tickers', nargs='*'); ap.add_argument('--from-dir'); ap.add_argument('--out', default='out/recommendations')
    ap.add_argument('--bars-dir'); ap.add_argument('--workers', type=int, default=os.cpu_count() or 1); ap.add_argument('--limit', type=int); ap.add_argument('--min-success', type=float, default=0.5)
    a = ap.parse_args(argv); tks = tickers_from(a)
    if not tks: sys.exit('沒有股票清單（--tickers 或 --from-dir）')
    t0 = time.time(); results = {}; errors = {}
    with ProcessPoolExecutor(max(1, a.workers), initializer=_init, initargs=(a.bars_dir,)) as ex:
        for i, (tk, r, err) in enumerate(ex.map(work, tks, chunksize=4), 1):
            if r: results[tk] = r
            else: errors[tk] = err
            if i % 50 == 0 or i == len(tks): print(f'{i}/{len(tks)} 成功 {len(results)} 失敗 {len(errors)}（{time.time() - t0:.0f}s）', flush=True)
    if len(results) < a.min_success * len(tks): sys.exit(f'成功 {len(results)}/{len(tks)} 低於 {a.min_success:.0%}，不寫檔')
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for tk, r in results.items(): (out / f'{tk}.json').write_text(json.dumps(r, ensure_ascii=False, separators=(',', ':')))
    keep = set(tks)
    for f in out.glob('*.json'):                                       # 不在清單內的舊檔刪掉（index.json 除外）
        if f.name != 'index.json' and f.stem not in keep: f.unlink()
    symbols = []
    for tk in tks:                                                     # 失敗的股票沿用上一次的檔案（若有）
        f = out / f'{tk}.json'
        if not f.exists(): continue
        r = json.loads(f.read_text()); symbols.append(dict(ticker=tk, asof=r['asof'], final={g['key']: g['final'] for g in r['ranges']}, fresh=tk in results))
    ref_asof = json.loads((ROOT / 'data' / 'reference.json').read_text()).get('asof')
    index = dict(version=VERSION, kind='SMA', generatedAt=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), referenceAsof=ref_asof,
                 requested=len(tks), updated=len(results), symbols=symbols, failed=[dict(ticker=k, reason=v) for k, v in sorted(errors.items())])
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')))
    print(f'寫入 {out}：更新 {len(results)}、沿用舊檔 {len(symbols) - len(results)}、失敗 {len(errors)}（{time.time() - t0:.0f}s）')

if __name__ == '__main__': main()
