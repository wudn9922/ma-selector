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
at.radio[0].set_value('複雜').run(); check(not at.exception, '回測切換到複雜策略沒有例外')
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
print('ALL PASS')
