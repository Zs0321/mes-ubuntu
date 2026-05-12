#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-finance-service/changjiang-bom-pricing/scripts')
from price_bom_xlsx import estimate_stator_bundle, is_stator_winding_component, KW_STATOR_MATERIAL, contains_any

# 模拟 test_stator_only.py 中的行
row = {
    "code": "T44200282.A0",
    "item": "定子组件",
    "material": "扁线4.12*1.92",
    "spec": "OD220mm，L135mm浸漆定子组件",
    "process": "",
    "qty": 1.0,
    "weight_kg": 5.6,
    "ext_weight_kg": 5.6,
    "base_total": 606.368,
}
context_rows = [row]

print(f"is_stator_winding_component(row) = {is_stator_winding_component(row)}")
print(f"contains_any(material, KW_STATOR_MATERIAL) = {contains_any(row['material'], KW_STATOR_MATERIAL)}")

result = estimate_stator_bundle(row, context_rows)
print(f"estimate_stator_bundle result = {result}")

# 模拟 test_full_bom3.py 中的两行
row1 = {
    "code": "T44200282.A0",
    "item": "定子组件",
    "material": "扁线4.12*1.92",
    "spec": "OD220mm，L135mm浸漆定子组件",
    "process": "",
    "qty": 1.0,
    "weight_kg": 5.6,
    "ext_weight_kg": 5.6,
    "base_total": 606.368,
}
row2 = {
    "code": "T44210291.A1",
    "item": "定子铁芯",
    "material": "B30AHV1500",
    "spec": "OD220mm，L135mm，三V",
    "process": "",
    "qty": 1.0,
    "weight_kg": 14.3,
    "ext_weight_kg": 14.3,
    "base_total": 72.215,
}
context_rows2 = [row1, row2]

result2 = estimate_stator_bundle(row1, context_rows2)
print(f"\nestimate_stator_bundle with stator_core result = {result2}")
