"""批次產生「建議均線」JSON（給 my-stock-screener 的 Atlas 圖表讀）：每檔一個 <ticker>.json＋index.json
流程與網頁預設完全相同（core/recommend.py）；不改任何規則。
用法：python scripts/build_recommendations.py --from-dir ../data --out ../docs/report/ma-selector [--workers 4] [--bars-dir 快取] [--limit 20]
  --from-dir：用目錄內 *.csv 的檔名當股票清單（略過 ^ 開頭的指數）；--tickers：直接列代號
  --bars-dir：從該目錄讀 <ticker>.csv（time/date,open,high,low,close,volume），沒有才抓 Yahoo 5 年日K
抓不到或資料不足的股票保留上一次的檔案。資料不足記入 index.json，90 天內不重抓，也不納入成功率；
成功率 < --min-success（預設 50%）時不寫任何檔案並以錯誤結束。
市場：.TW／.TWO 用台股成本（來回 0.585%）與台股基準池 data/reference_tw(_v2).parquet（檔案不存在就退回美股檔，記在 referencePool）；其餘用美股（0.1%、美股基準）。
hysteresis：讀 --out 裡該檔現有的 <ticker>.json 當 prev（讀不了就當沒有），規則見 core/recommend.py::_hold；設定簽章（scoring／referencePool／adjusted／costPct／kind）不同時不沿用。
分批（全市場約 7,000 檔時用）：--shard K/N 只重算 crc32(代號) % N == K 的股票，再加上還沒有輸出檔的股票（最多 --max-missing 檔，-1＝全部）；
其餘股票沿用現有檔案，index.json 仍列出清單內所有有檔案的股票。每月輪一個 K → 每檔每 N 個月更新一次。
--tickers-file：一行一個代號（# 開頭與空行略過）；--no-prune：不刪除清單外的舊檔（清單不完整時用）。"""
import argparse, datetime as dt, json, os, re, sys, time, zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import data, standardize, market
from core.recommend import recommend, VERSION, HYST_POINTS, scoring_id
ROOT = Path(__file__).resolve().parents[1]; SAFE = re.compile(r'^[A-Z0-9][A-Z0-9.\-]{0,31}$')
INSUFFICIENT_COOLDOWN_DAYS = 90
_POOLS = {}; _BARS = _OUT = None     # _POOLS：{'US'|'TW': (sma 池 dict, v2 池 dict 或 None)}；每個 worker 只載入一次，台股池不存在就與美股共用同一份（不重算）

def _load(path, v2, pool):
    f = Path(path)
    if not f.exists(): return None
    ref = pd.read_parquet(f)
    return dict(pool=pool, ref=ref, meta=json.loads(f.with_suffix('.json').read_text()) if f.with_suffix('.json').exists() else {},
                bests=standardize.ref_stock_bests_v2(ref) if v2 else standardize.ref_stock_bests(ref))   # 股票層級排名用：基準每檔的區間最高分

def _init(bars_dir, out_dir=None):
    global _POOLS, _BARS, _OUT
    _BARS = Path(bars_dir) if bars_dir else None; _OUT = Path(out_dir) if out_dir else None
    us = market.ref_files('US', ROOT); sma_us = _load(us['sma'], False, 'US')
    if sma_us is None: raise FileNotFoundError(us['sma'])                  # 美股基準一定要有（同過去）
    v2_us = _load(us['v2'], True, 'US')                                          # 近2年分數＋實驗選線 v2；基準不存在就不輸出這些欄位
    pool, _s, _v, v2pool = market.pick_pool('TW', ROOT); tw = market.ref_files('TW', ROOT)
    _POOLS = {'US': (sma_us, v2_us), 'TW': (_load(tw['sma'], False, 'TW') if pool == 'TW' else sma_us, _load(tw['v2'], True, 'TW') if v2pool == 'TW' else v2_us)}

def _prev(tk):
    """上一次發佈的 <out>/<ticker>.json（dict）；沒有或讀不了 → None"""
    if _OUT is None: return None
    try: r = json.loads((_OUT / f'{tk}.json').read_text()); return r if isinstance(r, dict) else None
    except Exception: return None

def _bars(tk):
    if _BARS and (_BARS / f'{tk}.csv').exists(): return data.load(_BARS / f'{tk}.csv')
    for i in range(3):
        try: return data.fetch_yahoo(tk)
        except Exception:
            if i == 2: raise
            time.sleep(2 * 2 ** i)

def work(tk):
    try:
        sma, v2 = _POOLS[market.market_of(tk)]
        bars = _bars(tk)
        r = recommend(bars, sma['ref'], tk, reference_asof=sma['meta'].get('asof'), ref_bests=sma['bests'], ref_v2=v2 and v2['ref'], ref_bests_v2=v2 and v2['bests'],
                      prev=_prev(tk), ref_pool=sma['pool'], ref_pool_v2=v2 and v2['pool'])
        return tk, r, None, None if r else len(bars)
    except Exception as e: return tk, None, f'{type(e).__name__}: {e}'[:200], None

def tickers_from(a):
    tks = list(a.tickers or [])
    if a.from_dir: tks += [p.stem for p in Path(a.from_dir).glob('*.csv')]
    if a.tickers_file: tks += [l.strip() for l in Path(a.tickers_file).read_text(encoding='utf-8').splitlines() if l.strip() and not l.lstrip().startswith('#')]
    tks = sorted({t.strip().upper() for t in tks if SAFE.match(t.strip().upper())})
    return tks[:a.limit] if a.limit else tks

def shard_of(tk, n): return zlib.crc32(tk.encode()) % n          # 固定的分批（與執行順序、清單內容無關）

def parse_shard(v):
    """'K/N' → (K, N)；'all' 或 None → None"""
    if v in (None, '', 'all'): return None
    k, n = (int(x) for x in str(v).split('/'))
    if not (n >= 1 and 0 <= k < n): raise ValueError(f'--shard 必須是 K/N 且 0 ≤ K < N，得到 {v!r}')
    return k, n

def load_insufficient(out):
    try:
        index = json.loads((out / 'index.json').read_text())
    except (OSError, ValueError):
        return {}
    records = index.get('insufficient') if isinstance(index, dict) else None
    if not isinstance(records, list):
        return {}
    result = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        ticker, bars, checked_at = (record.get(key) for key in ('ticker', 'bars', 'checkedAt'))
        if not isinstance(ticker, str) or not SAFE.fullmatch(ticker) or type(bars) is not int or bars < 0:
            continue
        try:
            checked_date = dt.date.fromisoformat(checked_at)
        except (TypeError, ValueError):
            continue
        result[ticker] = dict(ticker=ticker, bars=bars, checkedAt=checked_date.isoformat())
    return result


def plan(tks, out, shard, max_missing, *, insufficient=None, today=None):
    """→ (這次要算的代號, 分批資訊 dict)。先略過仍在冷卻期的股票。"""
    if today is None:
        today = dt.datetime.now(dt.timezone.utc).date()
    if insufficient is None:
        insufficient = load_insufficient(out)
    cooling = {
        ticker for ticker, record in insufficient.items()
        if 0 <= (today - dt.date.fromisoformat(record['checkedAt'])).days < INSUFFICIENT_COOLDOWN_DAYS
    }
    eligible = [ticker for ticker in tks if ticker not in cooling]
    skipped = len(tks) - len(eligible)
    if shard is None:
        return eligible, dict(shard=None, shards=1, inShard=len(eligible), missingAdded=0, missingLeft=0, insufficientSkipped=skipped)
    k, n = shard; mine = [t for t in eligible if shard_of(t, n) == k]; mset = set(mine)
    missing = [t for t in eligible if t not in mset and not (out / f'{t}.json').exists()]
    add = missing if max_missing < 0 else missing[:max_missing]; aset = set(add)
    return [t for t in eligible if t in mset or t in aset], dict(shard=k, shards=n, inShard=len(mine), missingAdded=len(add),
                                                              missingLeft=len(missing) - len(add), insufficientSkipped=skipped)

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument('--tickers', nargs='*'); ap.add_argument('--from-dir'); ap.add_argument('--out', default='out/recommendations')
    ap.add_argument('--bars-dir'); ap.add_argument('--workers', type=int, default=os.cpu_count() or 1); ap.add_argument('--limit', type=int); ap.add_argument('--min-success', type=float, default=0.5)
    ap.add_argument('--tickers-file'); ap.add_argument('--shard'); ap.add_argument('--max-missing', type=int, default=-1); ap.add_argument('--no-prune', action='store_true')
    a = ap.parse_args(argv); tks = tickers_from(a)
    if not tks: sys.exit('沒有股票清單（--tickers、--tickers-file 或 --from-dir）')
    out = Path(a.out)
    today = dt.datetime.now(dt.timezone.utc).date()
    insufficient = load_insufficient(out)
    todo, batch = plan(tks, out, parse_shard(a.shard), a.max_missing, insufficient=insufficient, today=today)
    print(f'清單 {len(tks)} 檔；這次重算 {len(todo)} 檔（分批 {batch}）', flush=True)
    t0 = time.time(); results = {}; errors = {}; insufficient_found = 0
    if todo:
        with ProcessPoolExecutor(max(1, a.workers), initializer=_init, initargs=(a.bars_dir, a.out)) as ex:
            for i, (tk, r, err, bars) in enumerate(ex.map(work, todo, chunksize=4), 1):
                if r:
                    results[tk] = r
                    insufficient.pop(tk, None)
                elif bars is not None:
                    insufficient[tk] = dict(ticker=tk, bars=bars, checkedAt=today.isoformat())
                    insufficient_found += 1
                else:
                    errors[tk] = err
                if i % 50 == 0 or i == len(todo): print(f'{i}/{len(todo)} 成功 {len(results)} 失敗 {len(errors)} 資料不足 {insufficient_found}（{time.time() - t0:.0f}s）', flush=True)
    attempted = len(results) + len(errors)
    if len(results) < a.min_success * attempted: sys.exit(f'成功 {len(results)}/{attempted} 低於 {a.min_success:.0%}，不寫檔')
    batch['insufficientFound'] = insufficient_found
    out.mkdir(parents=True, exist_ok=True)
    for tk, r in results.items(): (out / f'{tk}.json').write_text(json.dumps(r, ensure_ascii=False, separators=(',', ':')))
    keep = set(tks)
    if not a.no_prune:
        for f in out.glob('*.json'):                                   # 不在清單內的舊檔刪掉（index.json 除外）
            if f.name != 'index.json' and f.stem not in keep: f.unlink()
    symbols = []
    for tk in tks:                                                     # 失敗的股票沿用上一次的檔案（若有）
        f = out / f'{tk}.json'
        if not f.exists(): continue
        r = json.loads(f.read_text())   # 沿用的舊檔可能是舊版本，沒有的欄位用 .get（None）
        symbols.append(dict(ticker=tk, asof=r['asof'], final={g['key']: g['final'] for g in r['ranges']}, fresh=tk in results, market=r.get('market') or market.market_of(tk), referencePool=r.get('referencePool'),
                            unsuitable={g['key']: g.get('unsuitable') for g in r['ranges']}, held={g['key']: g.get('held') for g in r['ranges']}))
    asof = lambda name: json.loads((ROOT / 'data' / name).read_text()).get('asof') if (ROOT / 'data' / name).exists() else None
    index = dict(version=VERSION, kind='SMA', generatedAt=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), referenceAsof=asof('reference.json'), referenceAsofTW=asof('reference_tw.json'),
                 referenceV2Asof=asof('reference_v2.json'), costPct={m: round(c * 100, 4) for m, c in market.COSTS.items()}, scoring=scoring_id(), hystPoints=HYST_POINTS,
                 requested=len(tks), processed=len(todo), updated=len(results), refresh=batch, symbols=symbols,
                 failed=[dict(ticker=k, reason=v) for k, v in sorted(errors.items())],
                 insufficient=[record for tk, record in sorted(insufficient.items()) if a.no_prune or tk in keep])
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')))
    print(f'寫入 {out}：更新 {len(results)}、沿用舊檔 {len(symbols) - len(results)}、失敗 {len(errors)}（{time.time() - t0:.0f}s）')

if __name__ == '__main__': main()
