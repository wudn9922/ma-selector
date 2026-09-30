"""shim：final_select.py 以 `import bt_engine as bt` 匯入；權威實作是 bt_engine_v1.py（逐字原檔），這裡只做別名。"""
from bt_engine_v1 import run  # noqa: F401
