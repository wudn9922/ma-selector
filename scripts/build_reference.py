"""產生 data/reference.parquet：83 檔 × 96 條均線的「特徵值」分佈（新股票的分數用它換算百分位）
用法：python scripts/build_reference.py [--asof 2026-09-24] [--data-dir data_v]
每月更新一次（.github/workflows/build_reference.yml 可自動跑）"""
import argparse, json, sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import data, metrics, score
from core.universe import TICKERS

ap = argparse.ArgumentParser(); ap.add_argument('--asof'); ap.add_argument('--data-dir', default='data_v'); ap.add_argument('--out', default='data/reference.parquet')
a = ap.parse_args(); cache = Path(a.data_dir); cache.mkdir(exist_ok=True); frames, used, asofs = [], [], []
for tk in TICKERS:
    f = cache / f'{tk}.csv'
    try:
        if f.exists(): df = data.load(f, a.asof)
        else:
            df = data.fetch_yahoo(tk); df.drop(columns='date').to_csv(f, index=False); time.sleep(0.4)
            df = data.normalize(df, a.asof)
        if len(df) < 900: print(tk, '資料太短，略過', len(df)); continue
        M = metrics.compute_metrics(df); F = score.make_features(M); F.insert(0, 'ticker', tk); frames.append(F); used.append(tk); asofs.append(str(df.date.iloc[-1].date()))
        print(tk, len(df), flush=True)
    except Exception as e: print(tk, '失敗', e)
if len(frames) < 60: sys.exit(f'成功的股票只有 {len(frames)} 檔，不寫檔')
R = pd.concat(frames, ignore_index=True); Path(a.out).parent.mkdir(exist_ok=True); R.to_parquet(a.out, index=False)
Path(a.out).with_suffix('.json').write_text(json.dumps(dict(asof=max(asofs), tickers=used, n=len(R)), ensure_ascii=False))
print('寫入', a.out, R.shape)
