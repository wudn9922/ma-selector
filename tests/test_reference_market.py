"""TICKERS_TW 名單與 build_reference／build_reference_v2 的 --market 路徑解析測試（不連網、不寫檔）。用法：python tests/test_reference_market.py"""
import json, re, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from core import universe
import build_reference as br, build_reference_v2 as b2
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

SRC = Path('/tmp/claude-0/-home-user/b0ee7044-485f-5496-b795-ebba747cbf8c/scratchpad/gen/docs/report')   # 選股用的本機唯讀資料；CI 沒有

def test_tw_list_format():
    T = universe.TICKERS_TW
    check(len(T) == 100 and len(set(T)) == 100, 'TICKERS_TW 100 檔、無重複')
    check(all(re.fullmatch(r'[1-9]\d{3}\.(TW|TWO)', t) for t in T), '全部是 4 碼（首碼非 0）＋ .TW／.TWO')
    check(not set(T) & set(universe.TICKERS), '與美股池沒有交集')
    check(len(universe.TICKERS) == 83 and universe.TICKERS[:3] == ['AAPL', 'ABT', 'ACN'] and universe.TICKERS[-1] == 'ZTS', '美股 TICKERS 不變（83 檔）')

def test_tw_list_vs_source():
    if not (SRC / 'universe.json').exists(): print('SKIP 找不到選股來源檔（CI 預期如此），略過名單重現檢查'); return
    u = json.load(open(SRC / 'universe.json')); f = u['fields']; rows = [dict(zip(f, r)) for r in u['markets']['TW']['rows']]; by = {r['symbol']: r for r in rows}
    T = universe.TICKERS_TW; ind = Counter(by[t]['industry'] for t in T)
    check(all(t in by for t in T), '名單內的股票都在 universe.json')
    check(max(ind.values()) <= 12, f'每個 industry 最多 12 檔（最大 {max(ind.values())}）')
    bars = lambda t: json.load(open(SRC / 'ma-selector' / f'{t}.json')).get('bars') or 0
    check(all(bars(t) >= 1200 for t in T), '名單內 bars 全部 >= 1200')
    # 重現規則：結果必須與凍結名單完全相同（順序也相同）
    c = []
    for r in rows:
        p = SRC / 'ma-selector' / f"{r['symbol']}.json"
        if re.fullmatch(r'[1-9]\d{3}\.(TW|TWO)', r['symbol']) and p.exists() and (json.load(open(p)).get('bars') or 0) >= 1200 and r['turnover20']: c.append(r)
    c.sort(key=lambda r: (-r['turnover20'], r['symbol'])); cnt, sel = Counter(), []
    for r in c:
        if len(sel) == 100: break
        if cnt[r['industry']] >= 12: continue
        cnt[r['industry']] += 1; sel.append(r['symbol'])
    check(sel == list(T), '依規則（普通股、bars>=1200、turnover20 降序、每 industry <= 12）重算 → 與凍結名單完全一致')
    cut = by[T[-1]]['turnover20']; check(cut == 1015850784, f'第 100 檔 {T[-1]} turnover20 = {cut:,}')

def test_market_resolution():
    for mod, call in ((br, lambda m: br.resolve(m)), (b2, lambda m: b2.resolve(m))):
        t, o = call('us'); check(t == universe.TICKERS and o == ('data/reference.parquet' if mod is br else 'data/reference_v2.parquet'), f'{mod.__name__} --market us：美股 83 檔、路徑不變 {o}')
        t, o = call('tw'); check(t == universe.TICKERS_TW and o == ('data/reference_tw.parquet' if mod is br else 'data/reference_tw_v2.parquet'), f'{mod.__name__} --market tw：TICKERS_TW、路徑 {o}')
    check(br.resolve()[1] == 'data/reference.parquet' and b2.resolve()[1] == 'data/reference_v2.parquet', '預設（不給 market）＝us')
    check(br.resolve('us', 'EMA')[1] == 'data/reference_ema.parquet' and br.resolve('tw', 'EMA')[1] == 'data/reference_tw_ema.parquet', 'kind 與 market 可組合；us+EMA 路徑不變')
    check(br.resolve('tw', 'SMA', 'x/y.parquet')[1] == 'x/y.parquet' and b2.resolve('tw', 'x/y.parquet')[1] == 'x/y.parquet', '--out 優先')
    check(Path(br.resolve('tw')[1]).with_suffix('.json').as_posix() == 'data/reference_tw.json' and Path(b2.resolve('tw')[1]).with_suffix('.json').as_posix() == 'data/reference_tw_v2.json', '對應的 json 檔名')

def test_floor():
    check(br.min_ok(100) == 80 and b2.min_ok(100) == 80 and br.min_ok(83) == 67, '成功下限 80%（100 檔 → 80、83 檔 → 67）')

def _run(mod, tickers, fail, d, market='tw'):
    """假的 fetch_yahoo（合成資料；fail 內的代號丟例外），縮小名單後跑 main；回傳 (SystemExit code 或 None, 輸出檔路徑)"""
    import contextlib, io, hashlib
    from regression_synth import synth
    from core import data
    def fake(tk, *a, **k):
        if tk in fail: raise OSError('no network')
        return data.normalize(synth(int(hashlib.md5(tk.encode()).hexdigest(), 16) % 10000))
    old, oldT, oldS = data.fetch_yahoo, mod.TICKERS_TW, mod.time.sleep; data.fetch_yahoo = fake; mod.TICKERS_TW = tickers; mod.time.sleep = lambda s: None
    out = Path(d) / 'o.parquet'; code = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try: mod.main(['--market', market, '--data-dir', str(Path(d) / 'c'), '--out', str(out)])
            except SystemExit as e: code = e.code or 1
    finally: data.fetch_yahoo, mod.TICKERS_TW, mod.time.sleep = old, oldT, oldS
    return code, out

def test_floor_behaviour():
    """5 檔：4 檔成功（80%）→ 寫檔；3 檔成功 → exit 非 0 且不寫檔；全失敗 → 不寫檔。兩支腳本都測"""
    import tempfile, pandas as pd
    tk = ['1111.TW', '2222.TW', '3333.TWO', '4444.TW', '5555.TW']
    for mod in (br, b2):
        with tempfile.TemporaryDirectory() as d:
            code, out = _run(mod, tk, {'5555.TW'}, d)
            meta = json.loads(out.with_suffix('.json').read_text()) if out.exists() else {}
            check(code is None and out.exists() and meta.get('tickers') == tk[:4] and meta.get('n') == len(pd.read_parquet(out)) and meta.get('market') == 'tw', f'{mod.__name__}：4/5 成功 → 寫 parquet＋json（tickers 只含成功者、market=tw）')
            if mod is b2: check(meta.get('version') == 'v2', 'v2 json 有 version=v2')
        with tempfile.TemporaryDirectory() as d:
            code, out = _run(mod, tk, {'4444.TW', '5555.TW'}, d)
            check(code and not out.exists() and not out.with_suffix('.json').exists(), f'{mod.__name__}：3/5 成功（60%）→ 非 0 結束、不寫檔')
        with tempfile.TemporaryDirectory() as d:
            code, out = _run(mod, tk, set(tk), d)
            check(code and not out.exists() and not out.with_suffix('.json').exists(), f'{mod.__name__}：全部失敗 → 非 0 結束、不寫檔')
    # us 的 json 沒有 market 鍵：以原始碼確認（us 路徑會真的抓 83 檔，這裡不跑）
    src = (ROOT / 'scripts/build_reference.py').read_text(); check("({} if a.market == 'us' else dict(market=a.market))" in src, 'us 時 json 不加 market 鍵（格式不變）')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_'): v()
    print('ALL PASS')
