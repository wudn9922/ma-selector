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
print('ALL PASS')
