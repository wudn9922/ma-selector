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
print('ALL PASS')
