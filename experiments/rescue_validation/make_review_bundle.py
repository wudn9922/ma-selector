"""STRUCTURAL_RESCUE_FRESH_VALIDATION_100 的人工 review 圖（只做圖，不做任何判斷）。
只讀 commit A 已封存的 raw_outputs/<ticker>/bars.csv ＋ core/charts.py::chart_png；不抓 Yahoo、不跑 selector、不算 structural score／SAR。
圖與 manifest 都不含 winner／分數／SAR／PASS-FAIL。兩條 MA 用完全相同的日期範圍與分段（core 預設 bars=126, segs=4）。
用法：python experiments/rescue_validation/make_review_bundle.py"""
import hashlib, io, subprocess, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(ROOT))
from core import charts, data
RAW_COMMIT = '07023d68ffb56588e978f2bc65af063966d10067'
JOBS = [('PG', (22, 25)), ('FDX', (18, 21))]
BARS, SEGS = 126, 4
OUT = HERE / 'review_bundle'
sha = lambda b: hashlib.sha256(b).hexdigest()

def main():
    OUT.mkdir(exist_ok=True); lines = []; imgs = {}
    for tk, mas in JOBS:
        rel = f'experiments/rescue_validation/raw_outputs/{tk}/bars.csv'; blob = subprocess.run(['git', 'show', f'{RAW_COMMIT}:{rel}'], cwd=ROOT, capture_output=True, check=True).stdout
        assert sha((ROOT / rel).read_bytes()) == sha(blob), f'{rel} 與 commit A 不一致'
        df = data.normalize(pd.read_csv(io.BytesIO(blob), float_precision='round_trip')); N = len(df)
        for p in mas:
            png = charts.chart_png(df, p, f'{tk} SMA{p}', bars=BARS, segs=SEGS); (OUT / f'{tk}_SMA{p}.png').write_bytes(png)
            imgs[(tk, p)] = dict(sha=sha(png), src=sha(blob), n=N, first=str(df.date.iloc[0].date()), last=str(df.date.iloc[-1].date()), s0=str(df.date.iloc[N - BARS * SEGS].date()))
    L = ['# STRUCTURAL_RESCUE_FRESH_VALIDATION_100 — review bundle（只供人工看圖；不含任何選擇結果或分數）\n', f'- raw output commit（commit A）：`{RAW_COMMIT}`', f'- 圖表：`core/charts.py::chart_png`（既有語意：K 線、MA、±0.1ATR、糾結框、突破／影線／回測標記、持倉底色）',
         f'- chart parameters：bars={BARS}（每段）、segs={SEGS}（共 {BARS * SEGS} 根、約近兩年、四段由舊到新）；兩條 MA 日期範圍與分段完全相同；圖表標題只有「ticker＋SMA」\n',
         '| ticker | MA | 圖檔 | 圖片 SHA-256 | bars.csv 來源（commit A）SHA-256 | bars 總數 | 資料起訖 | 圖表起點日 |', '|---|---|---|---|---|---|---|---|']
    for (tk, p), v in imgs.items(): L.append(f"| {tk} | SMA{p} | `{tk}_SMA{p}.png` | `{v['sha']}` | `{v['src']}` | {v['n']} | {v['first']} ~ {v['last']} | {v['s0']} |")
    (OUT / 'review_manifest.md').write_text('\n'.join(L) + '\n', encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
