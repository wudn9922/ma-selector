"""網頁 smoke test（Streamlit AppTest，資料用合成股價；基準用 repo 的 data/reference.parquet）
檢查：代號輸入、gap 滑桿、候選表、最後選擇、判定圖、回測分頁（只做多）都能正常運作。
用法：python tests/test_app_smoke.py"""
import sys, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, select as sel
data.fetch_yahoo = lambda tk: data.normalize(synth(int(hashlib.md5(tk.encode()).hexdigest(), 16) % 10000))   # 沙盒連不到 Yahoo
from streamlit.testing.v1 import AppTest

def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
check(not at.exception, '首次載入（預設 AAPL）沒有例外')
check(not at.error, '沒有 st.error')
gap = [s for s in at.sidebar.slider if '候選門檻' in s.label][0]
check(gap.value == sel.GAP == 15 and gap.min == 3 and gap.max == 30, f'gap 滑桿預設 {gap.value}、範圍 {gap.min}–{gap.max}')
labels = [m.label for m in at.metric]; check('短期最後選擇' in labels and '長期最後選擇' in labels, f'最後選擇指標存在：{[ (m.label, m.value) for m in at.metric[2:4]]}')
final15 = [m.value for m in at.metric if m.label == '短期最後選擇'][0]
tables = [d for d in at.dataframe]; check(len(tables) >= 3, f'候選表（短／中／長）{len(tables)} 張')
cols = list(tables[0].value.columns); check('反手報酬(選參數)' in cols and '只做多簡單(參考)' in cols, f'候選表欄位含反手報酬與只做多參考：{cols}')
n15 = sum(len(t.value) for t in tables[:3])
gap.set_value(3).run(); check(not at.exception, 'gap=3 重新計算沒有例外')
n3 = sum(len(t.value) for t in at.dataframe[:3]); check(n3 <= n15, f'gap 3 的候選數 {n3} ≤ gap 15 的 {n15}')
gap = [s for s in at.sidebar.slider if '候選門檻' in s.label][0]; gap.set_value(30).run(); n30 = sum(len(t.value) for t in at.dataframe[:3]); check(n30 >= n15, f'gap 30 的候選數 {n30} ≥ gap 15 的 {n15}')
gap = [s for s in at.sidebar.slider if '候選門檻' in s.label][0]; gap.set_value(15).run()
check([m.value for m in at.metric if m.label == '短期最後選擇'][0] == final15, '滑桿調回 15 後最後選擇回到原值')
# 換代號
at.sidebar.text_input[0].set_value('MSFT').run(); check(not at.exception and not at.error, '輸入 MSFT 後沒有例外')
check(any('MSFT' in m.value for m in at.markdown), '頁面顯示 MSFT')
# 判定圖（tab2）與回測（tab3）
check(len(at.tabs) == 3, f'三個分頁：{[t.label for t in at.tabs]}')
imgs = at.get('image'); check(len(imgs) >= 1 and any(type(c).__name__ == 'Image' for c in at.tabs[1].children.values()), f'判定圖已渲染在「判定圖」分頁（{len(imgs)} 張）')
mets = [m.label for m in at.metric]; check('總報酬（複利）' in mets and '最大回撤' in mets and '獲利因子' in mets, '回測分頁指標存在')
[r for r in at.radio if r.label == '策略'][0].set_value('複雜').run(); check(not at.exception, '回測切換到複雜策略沒有例外')
at.number_input[0].set_value(20).run(); check(not at.exception, '檢視均線改成 20 沒有例外')
# ── 新增功能（只新增，不取代）：欄名、原始統計展開表、進場價 radio ──
at.sidebar.text_input[0].set_value('AAPL').run(); check(not at.exception and not at.error, '換回 AAPL 沒有例外')
tables = [d for d in at.dataframe]; cols0 = list(tables[0].value.columns)
check('糾結/穿插百分位(1y/2y/3y)' in cols0 and '突破' in cols0 and '二日' in cols0 and '回測' in cols0 and '雜訊' in cols0 and '快敗百分位(2y/3y)' in cols0, f'百分位欄位保留（含改名後的糾結/穿插百分位）：{cols0}')
check('穿插(短/中/長)' not in cols0 and '反手報酬(選參數)' in cols0 and '只做多簡單(參考)' in cols0 and '只做多複雜(參考)' in cols0, '舊欄名只改名、沒有刪掉其他欄')
raws = [t for t in tables if '突破成功率' in t.value.columns]; check(len(raws) == 3, f'短／中／長各有一張原始機率／比率表（{len(raws)} 張）')
rc = list(raws[0].value.columns); check(all(k in rc for k in ('均線', '突破成功率', '二日成功率', '回測成功率', '假突破比例', '糾結次數/年(1y/2y/3y)', '穿插日/年(1y/2y/3y)', '快敗率(1y/2y/3y)')), f'原始表欄位：{rc}')
check(any('n=' in str(v) or 'n=0' in str(v) for v in raws[0].value['突破成功率']), '成功率附 n')
check(any('不是發生機率' in c.value for c in at.caption), '有「percentile 不是發生機率」的說明')
check(any('BOX' in c.value and '尚未整合' in c.value for c in at.caption), '有 BOX 尚未整合的說明')
check(any('原始統計' in m.value for m in at.markdown), '判定圖頁有選定均線的原始統計摘要')
ent = [r for r in at.radio if r.label == '進場價']; check(len(ent) == 1 and ent[0].value == '跳空用開盤價（現行）' and list(ent[0].options) == ['跳空用開盤價（現行）', '固定均線門檻價'], f'回測頁有「進場價」radio，預設＝跳空用開盤價（現行）：{ent[0].options}')
def bt_metrics(): return [(m.label, m.value) for m in at.metric if m.label in ('總報酬（複利）', '最大回撤', '勝率', '筆數')]
base = bt_metrics(); ent[0].set_value('固定均線門檻價').run(); check(not at.exception, '切換「固定均線門檻價」沒有例外')
ent = [r for r in at.radio if r.label == '進場價'][0]; ent.set_value('跳空用開盤價（現行）').run(); check(bt_metrics() == base, '切回預設後結果與一開始完全相同')
at.number_input[1].set_value(1.5).run(); check(not at.exception, '雜訊區上緣可設 1.5（仍保留 0–5% 自由度）')
# ── EMA／SMA＋EMA 並列 ──
import os, tempfile
import pandas as pd
from core import metrics, score
def kind_radio(): return [r for r in at.sidebar.radio if r.label == '均線類型'][0]
def mvals(label): return [m.value for m in at.metric if m.label == label]
at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
check(kind_radio().value == 'SMA' and list(kind_radio().options) == ['SMA', 'EMA', 'SMA＋EMA 並列'], '均線類型預設 SMA')
check(mvals('短期最後選擇')[0].startswith('SMA') and mvals('短期最後選擇')[0] == final15, '預設 SMA：最後選擇仍是 SMA 且與原值相同')
check(not any('EMA' in c.value for c in at.caption), '預設 SMA 不顯示 EMA 說明')
os.environ['MA_SELECTOR_REF_EMA'] = str(Path(tempfile.mkdtemp()) / 'missing_reference_ema.parquet')   # 強制「沒有 EMA 基準」（不論 data/reference_ema.parquet 是否已存在）
kind_radio().set_value('EMA').run()
check(not at.exception, '選 EMA 但沒有 EMA 基準：沒有例外')
check(any('找不到 EMA 基準分佈' in w.value for w in at.warning), '選 EMA 但沒有 EMA 基準：顯示警告')
check(any(v.startswith('SMA') for v in mvals('短期最後選擇')) and not at.error, '選 EMA 但沒有 EMA 基準：退回只顯示 SMA')
kind_radio().set_value('SMA＋EMA 並列').run()
check(not at.exception and any('找不到 EMA 基準分佈' in w.value for w in at.warning), '並列模式沒有 EMA 基準：警告、不當機')
# 建一個暫時的 EMA 基準（6 檔合成股；不寫入 data/）
tmp = tempfile.mkdtemp(); ema_ref = Path(tmp) / 'reference_ema.parquet'
feats = []
for sd in range(1, 7):
    Me = metrics.compute_metrics(data.normalize(synth(sd)), kind='EMA'); feats.append(score.make_features(Me).assign(ticker=f'T{sd}'))
pd.concat(feats).to_parquet(ema_ref); os.environ['MA_SELECTOR_REF_EMA'] = str(ema_ref)
at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
kind_radio().set_value('EMA').run()
check(not at.exception and not at.error and not at.warning, 'EMA 模式（有基準）沒有例外／錯誤／警告')
check(all(v.startswith('EMA') for v in mvals('短期最後選擇') + mvals('長期最後選擇')) and len(mvals('短期最後選擇')) == 1, f'EMA 模式：最後選擇值為 EMA…：{mvals("短期最後選擇")}')
check(any('實驗性質' in c.value for c in at.caption), 'EMA 模式有實驗性質說明')
tb = [d for d in at.dataframe]; check(sum('反手報酬(選參數)' in t.value.columns for t in tb) == 3 and sum('突破成功率' in t.value.columns for t in tb) == 3, f'EMA 模式：候選表 3 張、原始表 3 張（共 {len(tb)} 表）')
check(any('EMA' in m.value and '最後選擇' in m.value for m in at.markdown), 'EMA 模式：區段標題用 EMA')
check(any(m.value.startswith('**EMA') and '原始統計' in m.value for m in at.markdown), 'EMA 模式：判定圖頁原始統計用 EMA')
kind_radio().set_value('SMA＋EMA 並列').run()
check(not at.exception and not at.error and not at.warning, '並列模式沒有例外／錯誤／警告')
check(mvals('短期最後選擇（SMA）')[0].startswith('SMA') and mvals('短期最後選擇（EMA）')[0].startswith('EMA') and mvals('長期最高分（EMA）') and mvals('股票適合度（短期最高分）（SMA）'), '並列模式：SMA 與 EMA 各一排指標')
tb = [d for d in at.dataframe]; check(sum('反手報酬(選參數)' in t.value.columns for t in tb) == 6 and sum('突破成功率' in t.value.columns for t in tb) == 6, f'並列模式：候選表 6 張、原始表 6 張（共 {len(tb)} 表）')
check(any(m.value.strip() == '#### SMA' or 'SMA' == m.value.strip('# ') for m in at.markdown) and any('EMA（實驗）' in m.value for m in at.markdown), '並列模式：有 SMA／EMA 小標題')
vk = [r for r in at.sidebar.radio if r.label == '檢視均線類型']; check(len(vk) == 1 and list(vk[0].options) == ['SMA', 'EMA'] and vk[0].value == 'SMA', '並列模式有「檢視均線類型」radio')
vk[0].set_value('EMA').run(); check(not at.exception and not at.error, '檢視均線類型改 EMA 沒有例外')
check(len(at.get('image')) >= 1 and any(m.value.startswith('**EMA') and '原始統計' in m.value for m in at.markdown), '檢視 EMA：判定圖與原始統計渲染')
cand_tabs = [t.value for t in at.dataframe if '反手報酬(選參數)' in t.value.columns]
ema_c = sorted({int(x) for t in cand_tabs[3:] for x in t['均線']}); cap_c = [c.value for c in at.sidebar.caption if c.value.startswith('候選')]
check(cap_c and cap_c[0] == '候選：' + '、'.join(map(str, ema_c)), f'側邊欄候選為 EMA 的候選：{cap_c}')
check(len([m for m in at.metric if m.label == '總報酬（複利）']) == 1, '檢視 EMA：回測指標存在')
[r for r in at.radio if r.label == '策略'][0].set_value('複雜').run(); check(not at.exception, '檢視 EMA：複雜策略回測沒有例外')
kind_radio().set_value('SMA').run(); check(not at.exception and mvals('短期最後選擇')[0].startswith('SMA'), '切回 SMA 沒有例外')
# ── 網址 ?ticker=（Atlas 連過來）與「在 Atlas 看圖表」連結 ──
aq = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180); aq.query_params['ticker'] = '2330.tw'; aq.run()
check(not aq.exception and not aq.error and aq.sidebar.text_input[0].value == '2330.TW', f'?ticker=2330.tw → 代號預填 2330.TW（{aq.sidebar.text_input[0].value}）')
check(any('atlas/?page=chart&tf=1D&symbol=2330.TW' in m.value for m in aq.markdown), '有連回 Atlas 圖表的連結')
aq.sidebar.text_input[0].set_value('MSFT').run(); check(aq.query_params.get('ticker') in ('MSFT', ['MSFT']), f'換代號後網址跟著更新：{aq.query_params.get("ticker")}')
ab = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180); ab.query_params['ticker'] = '<script>'; ab.run()
check(not ab.exception and ab.sidebar.text_input[0].value == 'AAPL', '不合法的 ?ticker= → 預設 AAPL')
# ── 實驗選線 v2（預設關閉；勾選後並列顯示；v2 基準不存在時只顯示說明）──
from core import score_v2, select_v2
def v2_box(a): return [c for c in a.sidebar.checkbox if c.label == '顯示實驗選線 v2']
def v2_exp(a): return [e for e in a.expander if e.label == '實驗選線 v2（尚未驗證，僅供比較）']
os.environ['MA_SELECTOR_REF_V2'] = str(Path(tempfile.mkdtemp()) / 'missing_reference_v2.parquet')   # 強制「沒有 v2 基準」（不論 data/reference_v2.parquet 是否已存在）
av = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
check(len(v2_box(av)) == 1 and v2_box(av)[0].value is False, '側邊欄有「顯示實驗選線 v2」，預設不勾')
check(not av.exception and not av.error and not v2_exp(av) and not any('v2' in str(m.label) for m in av.metric), '預設不勾：沒有 v2 區塊、現行輸出照舊')
v2_off_tables = [list(t.value.columns) for t in av.dataframe]; v2_off_metrics = [(m.label, m.value) for m in av.metric]; v2_off_charts = len(av.get('vega_lite_chart'))
v2_box(av)[0].set_value(True).run()
check(not av.exception and not av.error and not av.warning, '勾選 v2 但沒有 v2 基準：沒有例外／錯誤／警告')
check(any('v2 基準分佈尚未建立' in i.value for i in av.info) and len(v2_exp(av)) == 1, '沒有 v2 基準：顯示 st.info 說明（在 v2 區塊內）')
check([list(t.value.columns) for t in av.dataframe] == v2_off_tables and [(m.label, m.value) for m in av.metric] == v2_off_metrics, '沒有 v2 基準：其餘表格與指標和未勾選時完全相同')
# 建一個暫時的 v2 基準（6 檔合成股；不寫入 data/）
v2_ref = Path(tempfile.mkdtemp()) / 'reference_v2.parquet'
pd.concat([score_v2.make_features_v2(metrics.compute_metrics(data.normalize(synth(sd)))).assign(ticker=f'T{sd}') for sd in range(1, 7)]).to_parquet(v2_ref)
os.environ['MA_SELECTOR_REF_V2'] = str(v2_ref)
av = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
C2Y = '近2年分數(參考)'; on_tables = [list(t.value.columns) for t in av.dataframe]
check(not any(C2Y in c for c in v2_off_tables), '沒有 v2 基準：現行候選表沒有「近2年分數(參考)」欄')
check(not av.exception and not v2_exp(av) and [[x for x in c if x != C2Y] for c in on_tables] == v2_off_tables, '有 v2 基準但沒勾：不顯示 v2、其餘不變（只多「近2年分數(參考)」欄）')
cand_tabs = [t.value for t in av.dataframe if '分數(平滑)' in t.value.columns]
check(sum(C2Y in t.columns for t in cand_tabs) == 2 and C2Y not in cand_tabs[2].columns and list(cand_tabs[0].columns).index(C2Y) == list(cand_tabs[0].columns).index('分數(平滑)') + 1, '有 v2 基準：現行短期、中期候選表多「近2年分數(參考)」欄（緊接分數(平滑)），長期沒有')
v2_box(av)[0].set_value(True).run()
check(not av.exception and not av.error and not av.warning and not av.info, '勾選 v2（有基準）：沒有例外／錯誤／警告／說明')
check(len(v2_exp(av)) == 1, '出現「實驗選線 v2（尚未驗證，僅供比較）」區塊')
tv = [t for t in av.dataframe if '分數_2y' in t.value.columns or '分數_3y' in t.value.columns]
check(len(tv) in (2, 3) and sum('分數_2y' in t.value.columns for t in tv) >= 1 and sum('分數_3y' in t.value.columns for t in tv) == 1, f'v2 候選表：短期（含放寬時 2 張）＋中期 {len(tv)} 張')
sc = [t for t in tv if '分數_2y' in t.value.columns][0].value; mc = [t for t in tv if '分數_3y' in t.value.columns][0].value
check(list(sc.columns) == ['', '均線', '分數_2y', '分數_1y', '反手報酬', '反手報酬_1y', '反手回撤', '反手勝率', '反手筆數'], f'短期 v2 欄位：{list(sc.columns)}')
check(list(mc.columns) == ['', '均線', '分數_3y', '反手報酬', '反手回撤', '反手勝率', '反手筆數'], f'中期 v2 欄位：{list(mc.columns)}')
check((sc[''] == '★ 第一條').sum() == 1 and (mc[''] == '★').sum() == 1 and str(sc['反手報酬'].iloc[0]).endswith('%'), '第一條／中期 final 有 ★，報酬為百分比格式')
# 與直接呼叫 select_v2 比對（同一檔合成股、同一基準）
dfa = data.normalize(synth(int(hashlib.md5('AAPL'.encode()).hexdigest(), 16) % 10000)); Ma = metrics.compute_metrics(dfa); wsd = {'短': score.WS['短'], '長': score.WS['長']}
Ra = sel.select(dfa, score.score_table(Ma, pd.read_parquet(ROOT / 'data/reference.parquet'), wsd)); V = select_v2.select_v2(dfa, Ma, pd.read_parquet(v2_ref), ws=wsd, gap=sel.GAP, kind='SMA', long_result=Ra['長期'])
txt = ' '.join(m.value for m in av.markdown); s1, s2 = V['短期']['final1'], V['短期']['final2']
check(f"第一條 SMA{s1}" in txt and (f"第二條 SMA{s2}" in txt if s2 is not None else '找不到第二條' in txt) and f"v2：SMA{V['中期']['final']}" in txt and f"v2：SMA{V['長期']['final']}" in txt, f'摘要與 select_v2 相同：短 {s1}/{s2}、中 {V["中期"]["final"]}、長 {V["長期"]["final"]}')
cap = ' '.join(c.value for c in av.caption); check(f"SMA{Ra['短期']['final']}" in cap and f"SMA{Ra['中期']['final']}" in cap and f"現行：SMA{Ra['長期']['final']}" in cap, '旁邊列出現行選線的短／中／長 final')
T2a = score_v2.score_table_v2(Ma, pd.read_parquet(v2_ref), wsd).sort_values('period'); s2y = dict(zip(T2a['period'].tolist(), sel.smooth(T2a['分數_2y'].to_numpy()).tolist()))
ct = [t.value for t in av.dataframe if '近2年分數(參考)' in t.value.columns]
check(len(ct) == 2 and all(float(v) == round(s2y[int(p)], 1) for t in ct for p, v in zip(t['均線'], t['近2年分數(參考)'])), '「近2年分數(參考)」＝score_table_v2 的 分數_2y 平滑後四捨五入（短期、中期候選）')
vc = {c['均線']: c['分數_2y'] for c in V['短期']['cands']}; check(all(float(v) == vc[int(p)] for p, v in zip(ct[0]['均線'], ct[0]['近2年分數(參考)']) if int(p) in vc), '與 v2 短期候選表的 分數_2y 相同（重疊的週期）')
check(sorted(int(x) for x in sc['均線']) == sorted(c['均線'] for c in V['短期']['cands']) and sorted(int(x) for x in mc['均線']) == sorted(c['均線'] for c in V['中期']['cands']), 'v2 候選表的均線與 select_v2 相同')
vm = {m.label: m.value for m in av.metric}; su = V['suitability']
check(vm['v2 短期適合度（2 年最高分）'] == f"{su['short_2y']:.1f} / 100" and vm['v2 短期（1 年最高分）'] == f"{su['short_1y']:.1f} / 100" and vm['v2 中期（3 年最高分）'] == f"{su['mid_3y']:.1f} / 100", '適合度指標（2y／1y／3y 最高分）與 select_v2 相同')
check(len(av.get('vega_lite_chart')) == v2_off_charts + 1, f'v2 分數曲線圖多 1 張（{v2_off_charts} → {v2_off_charts + 1}）')
check([m.value for m in av.metric if m.label == '短期最後選擇'] == [f"SMA{Ra['短期']['final']}"], '勾選 v2 後，現行「短期最後選擇」不變')
gv = [s for s in av.sidebar.slider if '候選門檻' in s.label][0]; gv.set_value(5).run(); check(not av.exception and not av.error, '勾選 v2 後調 gap=5 沒有例外')
av.sidebar.text_input[0].set_value('MSFT').run(); check(not av.exception and not av.error and len(v2_exp(av)) == 1, '勾選 v2 後換代號沒有例外')
kr = [r for r in av.sidebar.radio if r.label == '均線類型'][0]; kr.set_value('EMA').run()
check(not av.exception and any('只支援 SMA' in i.value for i in av.info), '勾選 v2 且選 EMA：只顯示「只支援 SMA」說明')
# ── 股票層級排名（display-only；core/standardize.py）：只新增 caption，數字與直接呼叫 standardize 相同 ──
import re
from core import standardize as sd
def rank_caps(a): return [(m.group(1), float(m.group(2)), int(m.group(3)), int(m.group(4))) for c in a.caption for m in [re.search(r'^(.+?)最高分 ([\d.]+)：贏過 (\d+)% 的基準股票（(\d+) 檔；區間最高分對區間最高分）$', c.value)] if m]
def rank_caps_v2(a): return [(m.group(1), int(m.group(2)), int(m.group(3))) for c in a.caption for m in [re.search(r'^(.+年.+?)：贏過 (\d+)% 的基準股票（(\d+) 檔', c.value)] if m]
HELP = '基準＝83 檔大型股，排名＝這檔的區間最高分（平滑後）在 83 檔各自的區間最高分中贏過幾 %；只是參考，不影響選線。'
def pc0(B, c, x): return int(f"{sd.rank_pct(B[c].to_numpy(float), x)[0]:.0f}")   # 同 app 的 {:.0f} 顯示
def got(caps): return [(b, pc, n) for _l, b, pc, n in caps]
refa = pd.read_parquet(ROOT / 'data/reference.parquet'); Ba = sd.ref_stock_bests(refa, wsd); Sa = score.score_table(Ma, refa, wsd); ba = sd.range_bests(Sa)
ar = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
check(not ar.exception and not ar.error and not ar.warning, '股票層級排名：預設載入沒有例外／錯誤／警告')
caps = rank_caps(ar); check([c[0] for c in caps] == ['短期', '中期', '長期'], f'現行：短／中／長各有一句排名 caption：{[c.value for c in ar.caption if "贏過" in c.value]}')
check(got(caps) == [(round(ba[c], 1), pc0(Ba, c, ba[c]), 83) for c in ('短期', '中期', '長期')], f'caption 的最高分／百分位／n 等於直接用 standardize 算的 {got(caps)}')
check(abs(ba['短期'] - sel.suitability(Sa)[0]) < 1e-12 and abs(ba['長期'] - sel.suitability(Sa)[1]) < 1e-12 and f"{ba['短期']:.0f} / 100" in mvals('股票適合度（短期最高分）'), '短期／長期最高分等於既有適合度指標（排名用同一個數）')
check(any(HELP in c.value for c in ar.caption), '有股票層級排名的說明 caption')
check(mvals('短期最後選擇') == [f"SMA{Ra['短期']['final']}"] and not any('EMA' in c.value for c in ar.caption) and not rank_caps_v2(ar), '預設 SMA：最後選擇不變、沒有 EMA 字樣、沒有 v2 排名')
# 勾選 v2（有 v2 基準）：多 3 句 v2 排名，數字等於直接 standardize
v2_box(ar)[0].set_value(True).run(); check(not ar.exception and not ar.error and not ar.warning and not ar.info, '勾選 v2 後沒有例外')
B2 = sd.ref_stock_bests_v2(pd.read_parquet(v2_ref), wsd); su = V['suitability']; c2 = rank_caps_v2(ar); vm2 = {m.label: m.value for m in ar.metric}
check(len(c2) == 3 and [c[0] for c in c2] == ['短期（2 年最高分）', '短期（1 年最高分）', '中期（3 年最高分）'], f'v2 三個指標旁各一句排名 caption：{[c[0] for c in c2]}')
check([(c[1], c[2]) for c in c2] == [(pc0(B2, k, su[k]), len(B2)) for k in ('short_2y', 'short_1y', 'mid_3y')], f'v2 排名百分位與 n 等於直接 standardize：{[(c[1], c[2]) for c in c2]}')
check(vm2['v2 短期適合度（2 年最高分）'] == f"{su['short_2y']:.1f} / 100" and vm2['v2 中期（3 年最高分）'] == f"{su['mid_3y']:.1f} / 100", 'v2 適合度指標本身不變')
check(len(rank_caps(ar)) == 3 and got(rank_caps(ar)) == got(caps), '勾選 v2 後現行排名 caption 不變')
# 改權重：基準分佈重算，排名跟著 ws 走
sl = [x for x in ar.sidebar.slider if x.key == 's突破'][0]; sl.set_value(60).run(); check(not ar.exception, '調整權重後沒有例外')
ws2 = {'短': {k: (60 if k == '突破' else int(v * 100)) / 100 for k, v in score.WS['短'].items()}, '長': {k: int(v * 100) / 100 for k, v in score.WS['長'].items()}}
Bw = sd.ref_stock_bests(refa, ws2); bw = sd.range_bests(score.score_table(Ma, refa, ws2))
check(got(rank_caps(ar)) == [(round(bw[c], 1), pc0(Bw, c, bw[c]), 83) for c in ('短期', '中期', '長期')], f'調權重後 caption 等於以新權重直接 standardize：{got(rank_caps(ar))}')
# 並列模式（SMA 對 SMA 基準 83 檔、EMA 對自己的 EMA 基準）
ref_ema_df = pd.read_parquet(ema_ref); Me = metrics.compute_metrics(dfa, kind='EMA'); Se = score.score_table(Me, ref_ema_df, wsd); be = sd.range_bests(Se); Be = sd.ref_stock_bests(ref_ema_df, wsd)
ap = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run(); kind_radio_ = [r for r in ap.sidebar.radio if r.label == '均線類型'][0]; kind_radio_.set_value('SMA＋EMA 並列').run()
cp = rank_caps(ap); check(not ap.exception and not ap.error and len(cp) == 6 and [c[0] for c in cp] == ['短期（SMA）', '中期（SMA）', '長期（SMA）', '短期（EMA）', '中期（EMA）', '長期（EMA）'], f'並列：SMA、EMA 各 3 句排名：{[c[0] for c in cp]}')
check(got(cp[:3]) == got(caps) and got(cp[3:]) == [(round(be[c], 1), pc0(Be, c, be[c]), 6) for c in ('短期', '中期', '長期')], f'EMA 對自己的 EMA 基準排名（n=6），SMA 對 83 檔：{got(cp[3:])}')
check(len([c for c in ap.caption if HELP in c.value]) == 1, '並列模式說明 caption 只出現一次')
print('ALL PASS')
