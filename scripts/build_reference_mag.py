"""產生 data/reference_mag.parquet：突破幅度實驗的基準分佈（83 檔 × SMA15–110；現行 FEATS ＋ v2 FEATS_V2 ＋ 幅度／幅度_1y／2y／3y，只支援 SMA）
用法：python scripts/build_reference_mag.py [--asof 2026-09-24] [--data-dir data_v] [--out data/reference_mag.parquet]
現行 scripts/build_reference.py、build_reference_v2.py 與其 parquet 不動；.github/workflows/build_reference_mag.yml 每月＋push 自動跑"""
import argparse, json, sys, time
from pathlib import Path
import pandas as pd
sys.path[:0] = [str(Path(__file__).resolve().parents[1])]
from core import data, metrics, score_v2, score_mag
from core.universe import TICKERS

def features(M):
    """一列＝一個 (股票×均線)；欄位＝ticker, period, FEATS_ALL_MAG（現行＋v2＋幅度，無重複）"""
    F = score_mag.make_features_mag(M); F2 = score_v2.make_features_v2(M)
    for c in F2.columns:
        if c not in F.columns: F[c] = F2[c]
    return F[['period'] + score_mag.FEATS_ALL_MAG]

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--asof'); ap.add_argument('--data-dir', default='data_v'); ap.add_argument('--out', default='data/reference_mag.parquet')
    a = ap.parse_args(); cache = Path(a.data_dir); cache.mkdir(exist_ok=True); frames, used, asofs = [], [], []
    for tk in TICKERS:
        f = cache / f'{tk}.csv'
        try:
            if f.exists(): df = data.load(f, a.asof)
            else:
                df = data.fetch_yahoo(tk); df.drop(columns='date').to_csv(f, index=False); time.sleep(0.4)
                df = data.normalize(df, a.asof)
            if len(df) < 900: print(tk, '資料太短，略過', len(df)); continue
            F = features(metrics.compute_metrics(df)); F.insert(0, 'ticker', tk); frames.append(F); used.append(tk); asofs.append(str(df.date.iloc[-1].date()))
            print(tk, len(df), flush=True)
        except Exception as e: print(tk, '失敗', e)
    if len(frames) < 60: sys.exit(f'成功的股票只有 {len(frames)} 檔，不寫檔')
    R = pd.concat(frames, ignore_index=True); Path(a.out).parent.mkdir(exist_ok=True); R.to_parquet(a.out, index=False)
    Path(a.out).with_suffix('.json').write_text(json.dumps(dict(asof=max(asofs), tickers=used, n=len(R), version='mag'), ensure_ascii=False))
    print('寫入', a.out, R.shape)
