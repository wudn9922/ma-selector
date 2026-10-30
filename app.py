"""趨勢分界均線選參數 — Streamlit 網頁第一版"""
import datetime as dt, json, os, re
from urllib.parse import quote
from pathlib import Path
import numpy as np, pandas as pd, streamlit as st
from core import data, metrics, score, select as sel, backtest as bt, charts, rawstats
from core import score_v2, select_v2
from core.ma import moving_average

st.set_page_config(page_title="均線選參數", layout="wide")
ROOT = Path(__file__).parent
ATLAS_CHART = "https://wudn9922.github.io/my-stock-screener/atlas/?page=chart&tf=1D&symbol="   # Atlas 圖表（my-stock-screener 的 GitHub Pages）
def query_ticker():   # 網址 ?ticker=2330.TW（Atlas「在 ma-selector 查看詳情」連過來）；不合法就用 AAPL
    q = str(st.query_params.get("ticker", "")).strip().upper()
    return q if re.fullmatch(r"[A-Z0-9^][A-Z0-9.\-]{0,31}", q) else "AAPL"
def ref_path(kind):   # SMA：data/reference.parquet；EMA：data/reference_ema.parquet（環境變數 MA_SELECTOR_REF_EMA 可覆寫，測試用）；V2（實驗選線 v2）：data/reference_v2.parquet（MA_SELECTOR_REF_V2 可覆寫，測試用）
    if kind == 'V2': return Path(os.environ.get('MA_SELECTOR_REF_V2') or ROOT / 'data' / 'reference_v2.parquet')
    if kind == 'EMA': return Path(os.environ.get('MA_SELECTOR_REF_EMA') or ROOT / 'data' / 'reference_ema.parquet')
    return ROOT / 'data' / 'reference.parquet'

@st.cache_data(ttl=6 * 3600, show_spinner="抓取資料中…")
def fetch(tk, day): return data.fetch_yahoo(tk)          # day 只當 cache key：每天重抓
@st.cache_data(show_spinner="計算 96 條均線的指標（約 5–10 秒）…")
def calc_metrics(tk, last, n, kind, _df): return metrics.compute_metrics(_df, kind=kind)
@st.cache_data
def _read_ref(path, mtime):   # path、mtime 只當 cache key：檔案換了就重讀
    f = Path(path); meta = f.with_suffix('.json'); return pd.read_parquet(f), (json.loads(meta.read_text()) if meta.exists() else {})
def load_ref(kind):
    f = ref_path(kind)
    if not f.exists(): return None, None
    return _read_ref(str(f), f.stat().st_mtime)
@st.cache_data(show_spinner="候選均線回測中…")
def calc_select(tk, last, n, ws_key, gap, kind, _df, _S): return sel.select(_df, _S, gap=gap, kind=kind)   # 選參數用多空反手（events_v22）的回測
@st.cache_data(show_spinner="實驗選線 v2 計算中…")
def calc_select_v2(tk, last, n, ws_key, gap, ref_key, _df, _M, _ref, _ws, _long):   # 實驗選線 v2（只支援 SMA）；ref_key＝v2 基準檔的 mtime，檔案換了就重算
    out = select_v2.select_v2(_df, _M, _ref, ws=_ws, gap=gap, kind='SMA', long_result=_long)
    T = score_v2.score_table_v2(_M, _ref, _ws).sort_values('period')
    curve = pd.DataFrame({f'分數_{y}（平滑）': sel.smooth(T[f'分數_{y}'].to_numpy()) for y in ('1y', '2y', '3y')}, index=pd.Index(T['period'].to_numpy(), name='均線週期'))
    return out, curve
@st.cache_data(show_spinner="畫圖中…")
def render(tk, last, n, p, title, kind, _df): return charts.chart_png(_df, p, title, kind=kind)

ref, meta = load_ref('SMA')
st.markdown("#### 趨勢分界均線選參數")
if ref is None:
    st.error("找不到 data/reference.parquet（83 檔的基準分佈）。請到 GitHub → Actions → build-reference → Run workflow 產生，或在本機執行 `python scripts/build_reference.py`。"); st.stop()

# ── 側邊欄 ──
with st.sidebar:
    tk = st.text_input("股票代號", query_ticker()).strip().upper()
    kind_choice = st.radio("均線類型", ["SMA", "EMA", "SMA＋EMA 並列"], index=0, horizontal=True,
                           help="EMA 使用自己的 83 檔基準分佈（data/reference_ema.parquet）計算分數。選參數的規則（規則 B、短期 rescue）只在 SMA 上驗證過，EMA 結果屬於實驗性質。")
    up = st.file_uploader("（抓不到時）上傳日K CSV：time,open,high,low,close,volume", type='csv')
    with st.expander("分數權重（自動正規化為 100%）"):
        st.caption("短期（看近 1 年）")
        ws_s = {k: st.slider(k, 0, 100, int(v * 100), key='s' + k) for k, v in score.WS['短'].items()}
        st.caption("長期（看近 3 年）")
        ws_l = {k: st.slider(k, 0, 100, int(v * 100), key='l' + k) for k, v in score.WS['長'].items()}
        st.caption("中期＝短、長兩組權重平均（看近 2 年）")
    gap = st.slider("候選門檻：與最高分差距 ≤（分）", 3, 30, sel.GAP, 1, help="分數與該區間最高分相差在此範圍內的均線才列為候選（彼此至少差 3、最多 5 條）；預設 15")
    show_v2 = st.checkbox("顯示實驗選線 v2", False, help="實驗功能（尚未驗證）：短期 SMA15–45 用近 2 年選 2 條、中期 SMA46–70 用近 3 年選 1 條，長期沿用現行；與現行選線並列比較，不取代現行結果。只支援 SMA，需要 data/reference_v2.parquet。")
    st.caption(f"基準：{len((meta or {}).get('tickers', []))} 檔，資料到 {(meta or {}).get('asof', '?')}")
# ── 均線類型與基準分佈（EMA 基準不存在就退回只顯示 SMA）──
KINDS = {"SMA": ["SMA"], "EMA": ["EMA"], "SMA＋EMA 並列": ["SMA", "EMA"]}[kind_choice]
REFS = {'SMA': ref}; METAS = {'SMA': meta}
if 'EMA' in KINDS:
    REFS['EMA'], METAS['EMA'] = load_ref('EMA')
    if REFS['EMA'] is None:
        st.warning("找不到 EMA 基準分佈（data/reference_ema.parquet）。請到 GitHub → Actions → build-reference-ema → Run workflow 產生。目前只顯示 SMA。")
        KINDS = ['SMA']
    else:
        with st.sidebar: st.caption(f"EMA 基準：{len((METAS['EMA'] or {}).get('tickers', []))} 檔，資料到 {(METAS['EMA'] or {}).get('asof', '?')}")
if sum(ws_s.values()) == 0 or sum(ws_l.values()) == 0: st.warning("權重不能全為 0"); st.stop()
ws = {'短': {k: v / 100 for k, v in ws_s.items()}, '長': {k: v / 100 for k, v in ws_l.items()}}

# ── 資料 ──
try:
    df = data.normalize(pd.read_csv(up)) if up is not None else fetch(tk, dt.date.today().isoformat())
except Exception as e:
    st.error(f"抓不到 {tk} 的資料：{e}"); st.stop()
N = len(df); last = str(df.date.iloc[-1].date())
if N < 250 + 126: st.error(f"資料只有 {N} 根，太少"); st.stop()
if N < 756 + 110: st.warning(f"資料只有 {N} 根（約 {N/252:.1f} 年），長期／中期分數的視窗不足，僅供參考")
ws_key = json.dumps(ws, sort_keys=True); M, S, R, SUIT = {}, {}, {}, {}
for k in KINDS:
    M[k] = calc_metrics(tk, last, N, k, df); S[k] = score.score_table(M[k], REFS[k], ws)
    R[k] = calc_select(tk, last, N, ws_key, gap, k, df, S[k]); SUIT[k] = sel.suitability(S[k])

# ── 實驗選線 v2（勾選才算；只支援 SMA；基準 data/reference_v2.parquet 不存在就跳過）──
V2, V2_NOTE = None, None
if show_v2:
    if 'SMA' not in KINDS: V2_NOTE = ('info', "實驗選線 v2 只支援 SMA，請把均線類型改成 SMA（或 SMA＋EMA 並列）。")
    else:
        ref_v2, _meta_v2 = load_ref('V2')
        if ref_v2 is None: V2_NOTE = ('info', "v2 基準分佈尚未建立（data/reference_v2.parquet）。請到 GitHub → Actions → build-reference-v2 → Run workflow 產生，或在本機執行 `python scripts/build_reference_v2.py`。目前不顯示實驗選線 v2。")
        else:
            try: V2 = calc_select_v2(tk, last, N, ws_key, gap, str(ref_path('V2').stat().st_mtime), df, M['SMA'], ref_v2, ws, R['SMA']['長期'])
            except Exception as e: V2_NOTE = ('warning', f"實驗選線 v2 計算失敗：{e}")

if tk and st.query_params.get("ticker") != tk: st.query_params["ticker"] = tk   # 網址跟著代號，方便分享
st.markdown(f"**{tk}**　<span style='font-size:0.85rem;color:gray'>資料到 {last}（{N} 根）</span>　[在 Atlas 看圖表 ↗]({ATLAS_CHART}{quote(tk)})", unsafe_allow_html=True)
for k in KINDS:
    sfx = f"（{k}）" if len(KINDS) > 1 else ""; suit_s, suit_l = SUIT[k]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("股票適合度（短期最高分）" + sfx, f"{suit_s:.0f} / 100"); c2.metric("長期最高分" + sfx, f"{suit_l:.0f} / 100")
    c3.metric("短期最後選擇" + sfx, f"{k}{R[k]['短期']['final']}"); c4.metric("長期最後選擇" + sfx, f"{k}{R[k]['長期']['final']}")

pct = lambda x: f"{x*100:+.1f}%"
Mi = {k: M[k].set_index('period') for k in KINDS}; _C = df.close.to_numpy(float); _ATR = data.wilder_atr(df)
def cc_arrays(p, k='SMA'): return _C, moving_average(df.close, int(p), k), _ATR                  # 快敗率分母（明顯穿越次數）用；k＝均線類型
RAW_NOTE = ("成功率＝成功次數／已判定次數（括號內 n＝已判定次數；n=0 顯示「— (n=0)」不顯示 0%）。突破／二日／回測／假突破使用與評分相同的近 1 年（252 根）視窗；假突破比例＝假突破次數／(假突破＋已判定突破)。"
            "糾結次數/年、穿插日/年是**年化頻率（次/年）**，不是機率；快敗率＝明顯穿越均線後 5 天內又穿回的比例（括號內 n＝明顯穿越次數）。1y／2y／3y＝近 1／2／3 年視窗。")
ENTRY_LABELS = ["跳空用開盤價（現行）", "固定均線門檻價"]; ENTRY_MODE = {ENTRY_LABELS[0]: 'gap_open', ENTRY_LABELS[1]: 'fixed_band'}
tab1, tab2, tab3 = st.tabs(["候選與選擇", "判定圖", "回測"])
with tab1:
    st.caption(f"分數＝各項指標在 83 檔基準中的百分位加權；候選＝與最高分差 ≤{gap}、彼此差 ≥3、最多 5 條；選參數依據＝**多空反手**模擬（events_v22：一直有持倉，碰到反向邊界就反手，扣成本 0.1%）的報酬；"
               "最後選擇（★）：反手報酬距最佳 ≤5 個百分點者為 finalists，取結構分數（未四捨五入）最高者；完全相同才取較短的均線。短期另有固定的低頻 safeguard：結構分第一若被 5pp 排除、但結構分比上述選擇高 ≥10 分且反手報酬距最佳 ≤10 個百分點，改選它。只做多的簡單／複雜報酬僅供參考（「回測」分頁也是只做多）。")
    st.caption("**百分位欄位**（突破、二日、回測、雜訊、糾結/穿插百分位、快敗百分位）是「相對於 83 檔基準池（reference pool）的 percentile score」，**不是發生機率**；"
               "糾結（tangle.py 的糾結次數與穿插日）已經是均線評分的一部分。實際的成功率／比率／年化頻率在每個區段下方的「原始機率／比率」展開表。BOX（箱型）尚未整合：目前 repo 沒有可執行的正式 BOX 實作。")
    if 'EMA' in KINDS:
        st.caption("EMA 結果為實驗性質：規則 B 與短期 rescue 只在 SMA 上驗證過；EMA 分數是相對於 EMA 自己的 83 檔基準分佈。")
    for k in KINDS:
        if len(KINDS) > 1: st.markdown("#### SMA" if k == 'SMA' else "#### EMA（實驗）")
        Sk, Rk, Mik = S[k], R[k], Mi[k]
        for nm, lo, hi, W in sel.RANGES:
            r = Rk[nm]; st.markdown(f"**{nm}（{k}{lo}–{hi}，回測看近 {W//252} 年）**　最後選擇：{k}{r['final']}")
            rows = []
            for c in r['cands']:
                g = Sk[Sk.period == c['均線']].iloc[0]
                rows.append({'': '★' if c['均線'] == r['final'] else '', '均線': c['均線'], '分數(平滑)': c['分數'],
                             '突破': g['p突破'], '二日': g['p二日'], '回測': g['p回測'], '雜訊': g['p雜訊'],
                             '糾結/穿插百分位(1y/2y/3y)': f"{g['p穿插_1y']:.0f}/{g['p穿插_2y']:.0f}/{g['p穿插_3y']:.0f}",
                             '快敗百分位(2y/3y)': f"{g['p快敗_2y']:.0f}/{g['p快敗_3y']:.0f}",
                             '反手報酬(選參數)': pct(c['反手報酬']), '反手回撤': pct(c['反手回撤']), '反手勝率': f"{c['反手勝率']*100:.0f}%" if c['反手勝率'] == c['反手勝率'] else '—', '反手筆數': c['反手筆數'],
                             '只做多簡單(參考)': pct(c['簡單報酬']), '只做多複雜(參考)': pct(c['複雜報酬'])})
            st.dataframe(pd.DataFrame(rows).style.format({k_: '{:.0f}' for k_ in ('突破', '二日', '回測', '雜訊')}), hide_index=True, width='stretch')
            with st.expander(f"原始機率／比率／頻率（{nm}候選；實際統計，不是 percentile）"):
                raw_rows = [{'均線': c['均線'], **rawstats.raw_row(Mik.loc[c['均線']], rawstats.cross_counts(*cc_arrays(c['均線'], k)))} for c in r['cands']]
                st.dataframe(pd.DataFrame(raw_rows), hide_index=True, width='stretch')
                st.caption(RAW_NOTE)
        with st.expander("全部均線的分數" + (f"（{k}）" if len(KINDS) > 1 else "")):
            st.dataframe(Sk.round(1), hide_index=True, width='stretch')

    if show_v2:
        with st.expander("實驗選線 v2（尚未驗證，僅供比較）", expanded=True):
            if V2 is None: getattr(st, V2_NOTE[0])(V2_NOTE[1])
            else:
                v2, curve = V2; sh, md, lg, su = v2['短期'], v2['中期'], v2['長期'], v2['suitability']; cur = R['SMA']
                st.caption("實驗：短期 SMA15–45 用近 2 年（參考近 1 年）選 2 條；中期 SMA46–70 用近 3 年選 1 條；長期同現行。分數＝短期公式（你調的權重同樣套用）對 v2 基準分佈（data/reference_v2.parquet）的百分位；"
                           "候選、規則 B、短期 rescue 與現行相同，第二條需與第一條週期比例 ≥1.5。規則只在舊的短期 15–33／近 1 年驗證過，v2 尚未驗證，現行選線不受影響。")
                s2 = '找不到第二條' if sh['final2'] is None else f"SMA{sh['final2']}" + ('（放寬候選）' if sh['second_source'] == 'relaxed' else '')
                a1, a2, a3 = st.columns(3)
                a1.markdown(f"**短期（SMA15–45，近 2 年）**\n\nv2：第一條 SMA{sh['final1']}、第二條 {s2}"); a1.caption(f"現行（SMA15–33，近 1 年）：SMA{cur['短期']['final']}")
                a2.markdown(f"**中期（SMA46–70，近 3 年）**\n\nv2：SMA{md['final']}"); a2.caption(f"現行（SMA34–45，近 2 年）：SMA{cur['中期']['final']}")
                a3.markdown(f"**長期（SMA46–110，近 3 年）**\n\nv2：SMA{lg['final']}（同現行）"); a3.caption(f"現行：SMA{cur['長期']['final']}")
                b1, b2, b3 = st.columns(3)
                b1.metric("v2 短期適合度（2 年最高分）", f"{su['short_2y']:.1f} / 100"); b2.metric("v2 短期（1 年最高分）", f"{su['short_1y']:.1f} / 100"); b3.metric("v2 中期（3 年最高分）", f"{su['mid_3y']:.1f} / 100")
                def v2_rows(cs, cols, stars):
                    rows = [{'': stars.get(c['均線'], ''), **{k_: c[k_] for k_ in cols}} for c in cs]
                    for r_ in rows:
                        for k_ in ('反手報酬', '反手報酬_1y', '反手回撤'):
                            if k_ in r_: r_[k_] = pct(r_[k_])
                        r_['反手勝率'] = f"{r_['反手勝率']*100:.0f}%" if r_['反手勝率'] == r_['反手勝率'] else '—'
                    return pd.DataFrame(rows)
                SC = ['均線', '分數_2y', '分數_1y', '反手報酬', '反手報酬_1y', '反手回撤', '反手勝率', '反手筆數']; stars = {sh['final1']: '★ 第一條'}
                if sh['final2'] is not None: stars[sh['final2']] = '★ 第二條'
                st.markdown("**短期候選（近 2 年決定；反手報酬為近 2 年，_1y 為近 1 年參考）**")
                st.dataframe(v2_rows(sh['cands'], SC, stars), hide_index=True, width='stretch')
                if sh.get('relaxed'):
                    st.markdown("**短期放寬候選**　（候選內沒有與第一條週期比例 ≥1.5 者，改從區間內分數達門檻的週期找）")
                    st.dataframe(v2_rows(sh['relaxed'], SC, {sh['final2']: '★ 第二條'} if sh['second_source'] == 'relaxed' else {}), hide_index=True, width='stretch')
                st.markdown("**中期候選（近 3 年決定）**")
                st.dataframe(v2_rows(md['cands'], ['均線', '分數_3y', '反手報酬', '反手回撤', '反手勝率', '反手筆數'], {md['final']: '★'}), hide_index=True, width='stretch')
                st.markdown("**平滑後分數 vs 均線週期（SMA15–110；v2 短期看 15–45 的 1y／2y、中期看 46–70 的 3y）**")
                st.line_chart(curve)

with st.sidebar:
    k = st.radio("檢視均線類型", KINDS, horizontal=True) if len(KINDS) > 1 else KINDS[0]
    allp = [c['均線'] for nm in R[k] for c in R[k][nm]['cands']]
    default_p = R[k]['短期']['final']
    opts = sorted(set(allp)); p = st.number_input("檢視均線（判定圖／回測）", 15, 110, default_p, 1)
    st.caption("候選：" + "、".join(map(str, opts)))
p = int(p); Sv, Miv = S[k], Mi[k]; g = Sv[Sv.period == p].iloc[0]

with tab2:
    st.caption("近兩年 4 段（每段半年）由舊到新。雜訊區固定為 v22 規則（前日MA +1%／−1.5%）；回測分頁可以調整回測用的雜訊區。")
    def bt_line(nm, W):
        arr = [df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close', 'volume')]; ma_ = moving_average(df.close, p, k); atr_ = data.wilder_atr(df)
        sar = sel.sar_stats(*arr[:4], atr_, ma_, N - W)['報酬']; lo_ = {m: bt.run(*arr, ma_, atr_, lo=N - W, mode=m)[0]['總報酬'] for m in ('simple', 'complex')}
        return f"{nm} 反手 {pct(sar)}　只做多 簡{pct(lo_['simple'])}/複{pct(lo_['complex'])}"
    title = (f"{tk} {k}{p}｜分數 短{g['分數_短']:.0f} 中{g['分數_中']:.0f} 長{g['分數_長']:.0f}｜"
             f"突破{g['p突破']:.0f} 二日{g['p二日']:.0f} 回測{g['p回測']:.0f} 雜訊{g['p雜訊']:.0f} 穿插1y/2y/3y {g['p穿插_1y']:.0f}/{g['p穿插_2y']:.0f}/{g['p穿插_3y']:.0f} 快敗2y/3y {g['p快敗_2y']:.0f}/{g['p快敗_3y']:.0f}\n"
             f"{bt_line('近1年', 252)}｜{bt_line('近2年', 504)}")
    rr = rawstats.raw_row(Miv.loc[p], rawstats.cross_counts(*cc_arrays(p, k)))
    st.markdown(f"**{k}{p} 原始統計（實際機率／比率／頻率；不是 percentile）**　突破成功率 {rr['突破成功率']}｜二日成功率 {rr['二日成功率']}｜回測成功率 {rr['回測成功率']}｜假突破比例 {rr['假突破比例']}｜"
                f"糾結次數/年(1y/2y/3y) {rr['糾結次數/年(1y/2y/3y)']}｜穿插日/年(1y/2y/3y) {rr['穿插日/年(1y/2y/3y)']}｜快敗率(1y/2y/3y) {rr['快敗率(1y/2y/3y)']}")
    st.image(render(tk, last, N, p, title, k, df), width='stretch')
    if not charts.setup_font(): st.info("找不到中文字型，圖上的中文可能顯示成方框（請確認 packages.txt 的 fonts-noto-cjk）。")
    st.markdown("**圖例**"); st.text(charts.LEG)

with tab3:
    a1, a2, a3 = st.columns(3)
    mode = a1.radio("策略", ["簡單", "複雜"], horizontal=True); yrs = a1.radio("期間", ["近 1 年", "近 2 年"], horizontal=True)
    entry_lbl = a1.radio("進場價", ENTRY_LABELS, horizontal=True, help="只改「成交價」，訊號、停損、停利、早退都不變。跳空用開盤價（現行）：開盤已跳過上緣時，以開盤價成交；固定均線門檻價：一律以前日均線×(1＋上緣%)成交（空單：前日均線×(1－下緣%)），不因跳空改成開盤價。")
    x = a2.number_input("雜訊區上緣 %", 0.0, 5.0, 1.0, 0.1); c = a2.number_input("雜訊區下緣 %", 0.0, 5.0, 1.5, 0.1)
    cost = a3.number_input("單邊成本 %", 0.0, 1.0, 0.1, 0.05); tp = a3.number_input("停利門檻 %（複雜）", 1.0, 10.0, 3.0, 0.5)
    kw = {}
    if mode == "複雜":
        b1, b2, b3 = st.columns(3)
        kw = dict(ex_close=b1.checkbox("早退：當天收盤沒站上均線", True), ex_day2=b2.checkbox("早退：二日法則不成立", True), ex_vol=b3.checkbox("早退：沒有量增", False),
                  surge_pct=b1.number_input("急漲門檻：漲幅 %", 1.0, 20.0, 5.0, 0.5) / 100, surge_atr=b2.number_input("急漲門檻：ATR 倍數", 0.5, 5.0, 1.5, 0.1))
    W = 252 if yrs == "近 1 年" else 504
    O, H, L, C, V = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close', 'volume'))
    s, trades, eq = bt.run(O, H, L, C, V, moving_average(df.close, p, k), data.wilder_atr(df), lo=N - W, x=x / 100, c=c / 100,
                           cost=cost / 100, tp=tp / 100, mode='simple' if mode == "簡單" else 'complex', return_eq=True, entry_mode=ENTRY_MODE[entry_lbl], **kw)
    st.caption("若要測試「只在均線上方 1.0%～1.5% 進場」的版本：進場價選「固定均線門檻價」，並把「雜訊區上緣 %」設為 1.0～1.5（可逐一試 1.0、1.1、1.2、1.3、1.4、1.5）。上緣仍可設 0–5% 的任何值；預設「跳空用開盤價（現行）」與原本網頁結果完全相同。")
    m = st.columns(6)
    m[0].metric("總報酬（複利）", pct(s['總報酬'])); m[1].metric("最大回撤", pct(s['最大回撤'])); m[2].metric("勝率", '—' if np.isnan(s['勝率']) else f"{s['勝率']*100:.0f}%")
    m[3].metric("筆數", s['筆數']); m[4].metric("獲利因子", '∞' if np.isinf(s['獲利因子']) else f"{s['獲利因子']:.2f}"); m[5].metric("平均賺／賠", f"{s['平均賺']*100:+.1f}% / {s['平均賠']*100:+.1f}%")
    st.line_chart(pd.Series(eq[N - W:], index=df.date.iloc[N - W:], name="資金曲線（起點＝1）"))
    if trades:
        T = pd.DataFrame(trades); T['進場日'] = df.date.iloc[T.tin].dt.date.to_numpy(); T['出場日'] = df.date.iloc[T.tout].dt.date.to_numpy()
        T['類型'] = T.kind.map({'B': '突破', 'R': '回測'}); T['報酬'] = (T.ret * 100).round(2).astype(str) + '%'; T['持有天數'] = T.tout - T.tin
        T['未平倉'] = T.get('open', False) if 'open' in T else False
        st.dataframe(T[['進場日', '出場日', '類型', '報酬', '持有天數', '未平倉']], hide_index=True, width='stretch')
    else: st.info("這段期間沒有交易")
    st.caption("回測只做多；每筆以全額複利，成本為單邊。研究版預設值：雜訊區 +1%／−1.5%、成本 0.1%、停利 3%。")
