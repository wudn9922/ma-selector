"""core/data.py::fetch_yahoo 的股利還原（adjclose）測試，全部用合成 payload，不連網。用法：python tests/test_data_adjust.py"""
import io, json, sys, urllib.request
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT)]
from core import data
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

N = 6; T0 = 1700000000
def payload(adj='ok', close=None):
    close = close or [100., 101., 102., 50., 51., 52.]          # 第 4 根起股價腰斬（拆股後的資料，仍會被還原的股利影響）
    q = dict(open=[c - 1 for c in close], high=[c + 2 for c in close], low=[c - 3 for c in close], close=list(close), volume=[1000 * (i + 1) for i in range(N)])
    ind = dict(quote=[q])
    if adj == 'ok': ind['adjclose'] = [dict(adjclose=[c * (0.95 if i < 3 else 1.0) for i, c in enumerate(close)])]   # 第 3 根之後除息 5%
    elif adj is not None: ind['adjclose'] = adj
    return dict(chart=dict(result=[dict(meta=dict(gmtoffset=28800), timestamp=[T0 + 86400 * i for i in range(N)], indicators=ind)], error=None))

class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass
def fetch(pl, **kw):
    urls = []
    def fake(req, timeout=None): urls.append(req.full_url); return FakeResp(json.dumps(pl).encode())
    old = urllib.request.urlopen; urllib.request.urlopen = fake
    try: df = data.fetch_yahoo('2330.TW', **kw)
    finally: urllib.request.urlopen = old
    return df, urls[0]

def legacy(pl):
    """改動前的 fetch_yahoo 主體（逐字）"""
    res = pl["chart"]["result"][0]; q, off = res["indicators"]["quote"][0], res["meta"].get("gmtoffset", 0)
    df = pd.DataFrame({"time": [pd.to_datetime(t + off, unit="s").strftime("%Y-%m-%d") for t in res["timestamp"]],
                       "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]})
    return data.normalize(df)

def test_adjusted():
    pl = payload(); df, url = fetch(pl)
    check('events=div%2Csplits' in url and 'range=5y' in url, '調整模式：URL 帶 events=div%2Csplits')
    raw = legacy(pl); a = pl['chart']['result'][0]['indicators']['adjclose'][0]['adjclose']; f = np.array(a) / raw.close.to_numpy()
    for c in ('open', 'high', 'low', 'close'): check(np.allclose(df[c], raw[c] * f), f'{c} 乘上 adjclose/close')
    check(np.allclose(df.close, a), 'close 還原後等於 adjclose')
    check((df.volume == raw.volume).all() and (df.time == raw.time).all(), 'volume 與日期不變')
    check(df.attrs['adjusted'] is True, "attrs['adjusted'] is True")
    check(np.isclose(df.close.iloc[2] / df.close.iloc[1], 102 / 101), '除息前後同一天比例不受影響（同在除息前）')

def test_off_identical():
    for pl in (payload(), payload(None), payload([])):
        df, url = fetch(pl, adjust=False); old = legacy(pl)
        check('events' not in url, 'adjust=False：URL 與舊版相同（不帶 events）')
        pd.testing.assert_frame_equal(df, old, check_exact=True)
        check(df.equals(old) and df.to_csv(index=False) == old.to_csv(index=False) and list(df.dtypes) == list(old.dtypes), 'adjust=False 與舊版逐位元組相同（frame／csv／dtypes）')
        check(df.attrs['adjusted'] is False, "adjust=False → attrs['adjusted'] is False")

def test_fallback():
    base = legacy(payload())
    ok = payload()['chart']['result'][0]['indicators']['adjclose'][0]['adjclose']
    cases = {'缺 adjclose': None, '空 list': [], 'adjclose 不是 list': 'x', 'adjclose 區塊是 dict 少 key': [dict()], 'adjclose[0] 為 None': [None], 'adjclose 欄位是 None': [dict(adjclose=None)],
             '長度不符(短)': [dict(adjclose=ok[:-1])], '長度不符(長)': [dict(adjclose=ok + [1.])], 'adjclose 有 None': [dict(adjclose=ok[:2] + [None] + ok[3:])],
             'adjclose 有 0': [dict(adjclose=ok[:2] + [0.] + ok[3:])], 'adjclose 有負值': [dict(adjclose=ok[:2] + [-1.] + ok[3:])], 'adjclose 有字串': [dict(adjclose=ok[:2] + ['abc'] + ok[3:])],
             'adjclose 有 NaN': [dict(adjclose=ok[:2] + [float('nan')] + ok[3:])], 'adjclose 有 inf': [dict(adjclose=ok[:2] + [float('inf')] + ok[3:])]}
    for name, adj in cases.items():
        pl = payload(adj) if adj is not None else payload(None)
        if isinstance(adj, str): pl['chart']['result'][0]['indicators']['adjclose'] = [dict(adjclose=adj)]
        df, _ = fetch(pl); pd.testing.assert_frame_equal(df, base, check_exact=True); check(df.attrs['adjusted'] is False, f"{name} → 不還原、不崩潰、adjusted False")
    pl = payload(); del pl['chart']['result'][0]['indicators']['adjclose'][0]['adjclose']; df, _ = fetch(pl)
    check(df.attrs['adjusted'] is False, 'adjclose 區塊缺 adjclose key → 不還原')
    for bad_close in (0., -5.):                                                  # close 非正 → 整條視為無法還原
        pl = payload(close=[100., 101., bad_close, 50., 51., 52.]); df, _ = fetch(pl)
        check(df.attrs['adjusted'] is False and df.close.iloc[2] == bad_close, f'close={bad_close} → 不還原')

def test_null_close_bar():
    """close 為 null 的那根（normalize 會丟）不影響其他根的還原；adjclose 同一根也是 null"""
    pl = payload(); r = pl['chart']['result'][0]; r['indicators']['quote'][0]['close'][3] = None; r['indicators']['adjclose'][0]['adjclose'][3] = None
    df, _ = fetch(pl)
    check(df.attrs['adjusted'] is True and len(df) == N - 1, 'close null 且 adjclose null：該根被丟掉，其餘仍還原')
    ref = legacy(pl); f = np.array([.95, .95, .95, 1., 1.]); check(np.allclose(df.close, ref.close * f), '其餘 5 根仍乘上 factor')
    pl = payload(); r = pl['chart']['result'][0]; r['indicators']['quote'][0]['close'][3] = None            # close null 但 adjclose 有值：factor 用 1.0、該根丟掉
    df, _ = fetch(pl); check(df.attrs['adjusted'] is True and len(df) == N - 1, 'close null、adjclose 有值：該根丟掉，仍還原')
    pl = payload(); r = pl['chart']['result'][0]; r['indicators']['adjclose'][0]['adjclose'][3] = None       # close 有值、adjclose null：整條不還原
    df, _ = fetch(pl); check(df.attrs['adjusted'] is False and len(df) == N, 'close 有值、adjclose null：整條不還原')

def test_normalize_attrs():
    df = pd.DataFrame({'time': ['2026-01-02', '2026-01-03'], 'open': [1., 2.], 'high': [1., 2.], 'low': [1., 2.], 'close': [1., 2.], 'volume': [1, 2]})
    df.attrs['adjusted'] = True
    check(data.normalize(df).attrs.get('adjusted') is True and data.normalize(df, '2026-01-02').attrs.get('adjusted') is True, 'normalize（含 asof 截斷）保留 attrs')
    check(data.normalize(data.normalize(df)).attrs.get('adjusted') is True, '再次 normalize 仍保留')
    p = ROOT / 'tests' / '_tmp_adjust.csv'; df.to_csv(p, index=False)
    try: check('adjusted' not in data.load(p).attrs, 'load(CSV) 不帶 adjusted（行為不變）')
    finally: p.unlink()

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_'): v()
    print('ALL PASS')
