"""產生 data/reference.parquet：83 檔 × 96 條均線的「特徵值」分佈（新股票的分數用它換算百分位）
用法：python scripts/build_reference.py [--asof 2026-09-24] [--data-dir data_v] [--kind SMA|EMA]
每月更新一次（.github/workflows/build_reference.yml 可自動跑）；--kind EMA 寫 data/reference_ema.parquet／.json（build_reference_ema.yml）"""
import argparse, json, sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import data, metrics, score
from core.ma import KINDS
from core.universe import TICKERS

def default_out(kind): return 'data/reference.parquet' if kind == 'SMA' else f'data/reference_{kind.lower()}.parquet'   # SMA 路徑維持原樣

ap = argparse.ArgumentParser(); ap.add_argument('--asof'); ap.add_argument('--data-dir', default='data_v'); ap.add_argument('--out'); ap.add_argument('--kind', choices=KINDS, default='SMA')
a = ap.parse_args(); a.out = a.out or default_out(a.kind); cache = Path(a.data_dir); cache.mkdir(exist_ok=True); frames, used, asofs = [], [], []
for tk in TICKERS:
    f = cache / f'{tk}.csv'
    try:
        if f.exists(): df = data.load(f, a.asof)
        else:
            df = data.fetch_yahoo(tk); df.drop(columns='date').to_csv(f, index=False); time.sleep(0.4)
            df = data.normalize(df, a.asof)
        if len(df) < 900: print(tk, '資料太短，略過', len(df)); continue
        M = metrics.compute_metrics(df, kind=a.kind); F = score.make_features(M); F.insert(0, 'ticker', tk); frames.append(F); used.append(tk); asofs.append(str(df.date.iloc[-1].date()))
        print(tk, len(df), flush=True)
    except Exception as e: print(tk, '失敗', e)
if len(frames) < 60: sys.exit(f'成功的股票只有 {len(frames)} 檔，不寫檔')
R = pd.concat(frames, ignore_index=True); Path(a.out).parent.mkdir(exist_ok=True); R.to_parquet(a.out, index=False)
Path(a.out).with_suffix('.json').write_text(json.dumps(dict(asof=max(asofs), tickers=used, n=len(R), **({} if a.kind == 'SMA' else dict(kind=a.kind))), ensure_ascii=False))
print('寫入', a.out, R.shape)
