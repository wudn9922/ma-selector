"""市場設定：代號→市場、來回交易成本、基準檔路徑（只放設定，不含計算）
COSTS＝每筆「來回」成本（比例）。台股 0.585%＝牌告手續費 0.1425%×2（買賣各一次）＋賣出證交稅 0.3%，不含券商折扣（保守）；美股沿用 0.1%（舊行為）。
成本只影響回測的交易報酬（events／backtest／select 的反手報酬）；metrics／分數／基準檔與成本無關。"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
COSTS = {'TW': 0.00585, 'US': 0.001}
MARKETS = tuple(COSTS)

def market_of(ticker):
    """代號 → 'TW'（後綴 .TW／.TWO，不分大小寫）或 'US'（其餘）"""
    t = str(ticker).strip().upper(); return 'TW' if t.endswith('.TW') or t.endswith('.TWO') else 'US'

def cost_of(ticker): return COSTS[market_of(ticker)]

def ref_files(market, root=ROOT):
    """市場 → 該市場基準檔路徑 dict(sma, v2)（不檢查是否存在；json 為同名 .json）"""
    d = Path(root) / 'data'; sfx = '' if market == 'US' else '_tw'
    return dict(sma=d / f'reference{sfx}.parquet', v2=d / f'reference{sfx}_v2.parquet')

def pick_pool(market, root=ROOT):
    """市場 → (sma 基準池, sma 路徑, v2 路徑, v2 基準池)。台股且 reference_tw.parquet 存在 → 'TW'，否則退回美股檔（同過去）；
    v2 與 sma 各自獨立判斷：台股 v2 檔不存在就用美股 v2（第四項＝v2 實際用的池）"""
    us, tw = ref_files('US', root), ref_files('TW', root)
    pool = 'TW' if market == 'TW' and tw['sma'].exists() else 'US'
    v2_pool = 'TW' if market == 'TW' and tw['v2'].exists() else 'US'
    return pool, (tw if pool == 'TW' else us)['sma'], (tw if v2_pool == 'TW' else us)['v2'], v2_pool
