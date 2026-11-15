"""產生 data/reference_v2.parquet：實驗選線 v2 的基準分佈（83 檔 × SMA15–110，1y／2y／3y 三視窗特徵，只支援 SMA）
用法：python scripts/build_reference_v2.py [--asof 2026-09-24] [--data-dir data_v] [--out data/reference_v2.parquet] [--market us|tw]
現行 scripts/build_reference.py 與 data/reference.parquet 不動；.github/workflows/build_reference_v2.yml 每月＋push 自動跑
--market tw：台股池（TICKERS_TW）寫 data/reference_tw_v2.parquet／.json；成功的股票不到 80% 就不寫檔（exit 1）"""
import argparse, json, math, sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import data, metrics, score_v2
from core.universe import TICKERS, TICKERS_TW

MIN_OK = .8      # 成功比例下限，低於就不覆蓋好檔

def default_out(market='us'): return 'data/reference_v2.parquet' if market == 'us' else 'data/reference_tw_v2.parquet'   # us 路徑維持原樣

def resolve(market='us', out=None):
    """→ (tickers, out_path)；不做任何 I/O（測試用）"""
    return list(TICKERS if market == 'us' else TICKERS_TW), out or default_out(market)

def min_ok(n): return math.ceil(MIN_OK * n)

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument('--asof'); ap.add_argument('--data-dir', default='data_v'); ap.add_argument('--out'); ap.add_argument('--market', choices=('us', 'tw'), default='us')
    a = ap.parse_args(argv); tickers, a.out = resolve(a.market, a.out); cache = Path(a.data_dir); cache.mkdir(exist_ok=True); frames, used, asofs, unadj = [], [], [], []
    for tk in tickers:
        f = cache / f'{tk}.csv'
        try:
            if f.exists(): df = data.load(f, a.asof)
            else:
                df = data.fetch_yahoo(tk); df.drop(columns='date').to_csv(f, index=False); time.sleep(0.4)
                if not df.attrs.get('adjusted'): unadj.append(tk)
                df = data.normalize(df, a.asof)
            if len(df) < 900: print(tk, '資料太短，略過', len(df)); continue
            M = metrics.compute_metrics(df); F = score_v2.make_features_v2(M); F.insert(0, 'ticker', tk); frames.append(F); used.append(tk); asofs.append(str(df.date.iloc[-1].date()))
            print(tk, len(df), flush=True)
        except Exception as e: print(tk, '失敗', e)
    if unadj: print('警告：以下股票 Yahoo 沒給 adjclose，未還原股利：', ' '.join(unadj))
    if len(frames) < min_ok(len(tickers)): sys.exit(f'成功的股票只有 {len(frames)}／{len(tickers)} 檔（至少要 {min_ok(len(tickers))}），不寫檔')
    R = pd.concat(frames, ignore_index=True); Path(a.out).parent.mkdir(exist_ok=True); R.to_parquet(a.out, index=False)
    extra = {} if a.market == 'us' else dict(market=a.market)
    Path(a.out).with_suffix('.json').write_text(json.dumps(dict(asof=max(asofs), tickers=used, n=len(R), version='v2', **extra), ensure_ascii=False))
    print('寫入', a.out, R.shape)

if __name__ == '__main__': main()
