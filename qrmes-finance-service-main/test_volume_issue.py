#!/usr/bin/env python3
import os
os.environ["DASHSCOPE_API_KEY"] = ""
os.environ["PRICING_QWEN_TIMEOUT"] = "5"
os.environ["PRICING_QWEN_TIMEOUT_RETRY"] = "0"

import sys
sys.path.insert(0, '/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-finance-service/app_web')
sys.path.insert(0, '/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-finance-service')

from backend.services.finance_skill_quote_service import FinanceSkillQuoteService

class FakeAIRouteService:
    is_ready = False
    max_workers = 1
    def load_skill_workflow_hint(self):
        return "price_bom mandatory; gap/format/volume on demand."
    def plan_script_usage(self, plan_input):
        return {"selected_scripts": ["price_bom_xlsx.py", "model_volume_pricing.py"], "registry": ["price_bom_xlsx.py", "model_volume_pricing.py"]}
    def prepare_staged_pricing_input(self, item):
        return item
    def estimate_item(self, item):
        return {"unit_price": 0, "confidence": 0, "reasoning": "", "source": "fake"}

items = [
    {"name":"轴承压板","code":"T45170281.A0","spec":"内外径51×108mm","material":"Q235A发黑","weight_kg":0.107,"process":"","qty":1},
    {"name":"前端盖","code":"T46110282.A0","spec":"OD220mm前端盖（028-B电机）","material":"A356-T6","weight_kg":3.82,"process":"低压模具","qty":1},
    {"name":"旋变定子压板","code":"T46170021.A1","spec":"厚度2 mm","material":"Q235A","weight_kg":0.014,"process":"","qty":1},
    {"name":"轴承","code":"T19100018.A0","spec":"6206-2Z/AEM3/C3GJN","material":"轴承钢","weight_kg":0.3,"process":"","qty":1},
    {"name":"轴承","code":"T19100019.A0","spec":"6309-2Z/AEM3/C3GJN","material":"轴承钢","weight_kg":0.36,"process":"","qty":1},
    {"name":"油封","code":"T27080282.A0","spec":"SA1J 45×68×12 GJ2668F2","material":"日本NOK油封","weight_kg":None,"process":"","qty":1},
    {"name":"波形弹簧","code":"T19170001.A1","spec":"JB/T 7590-2005 （D62/发蓝）","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"内六角圆柱头螺钉","code":"T19020102.A1","spec":"GB/T 70.1-2008（M4X12/8.8级/达克罗）","material":"","weight_kg":None,"process":"","qty":4},
    {"name":"内六角圆柱头螺钉","code":"T19020104.A1","spec":"GB/T 70.1-2008（M5x16/8.8级/达克罗）","material":"","weight_kg":None,"process":"","qty":4},
    {"name":"内六角圆柱头螺钉","code":"T19020111.A1","spec":"GB/T 70.1-2008（M8x30/8.8级/达克罗）","material":"","weight_kg":None,"process":"","qty":20},
    {"name":"六角法兰面螺栓 加大系列 B级","code":"T19020414.A1","spec":"GB/T 5789（ M5×20/10.9级/达克罗）","material":"","weight_kg":None,"process":"","qty":5},
    {"name":"六角法兰面螺栓","code":"T19020303.A1","spec":"GB/T 5787-2000（M8X20/8.8级/达克罗/带齿）","material":"","weight_kg":None,"process":"","qty":2},
    {"name":"弹簧垫圈","code":"T19030101.A1","spec":"GB/T 93-1987（4/达克罗）","material":"","weight_kg":None,"process":"","qty":4},
    {"name":"弹簧垫圈","code":"T19030102.A1","spec":"GB/T 93-1987（5/达克罗）","material":"","weight_kg":None,"process":"","qty":4},
    {"name":"弹簧垫圈","code":"T19030104.A1","spec":"GB/T 93-1987（8/达克罗）","material":"","weight_kg":None,"process":"","qty":20},
    {"name":"轴用弹性挡圈","code":"T19140004.A0","spec":"GB/T 894-2017（45）","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"水嘴","code":"T46140281.A0","spec":"D20直水嘴（028-B电机）","material":"6061-T6","weight_kg":0.07,"process":"低压模具","qty":1},
    {"name":"弯头水嘴","code":"T46140371.A0","spec":"D20弯管，6061","material":"6061-T6","weight_kg":0.07,"process":"低压模具","qty":1},
    {"name":"普通平键","code":"T19180001.A1","spec":"GB/T 1096-2003（A2X2X8）","material":"45","weight_kg":None,"process":"","qty":1},
    {"name":"O型圈","code":"T27080019.A0","spec":"φ221×φ2.65","material":"氟橡胶","weight_kg":None,"process":"","qty":2},
    {"name":"堵头","code":"T49060281.A0","spec":"M20×1.5","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"线束总成","code":"U22170112.A0","spec":"高速油泵旋变线束","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"线束总成","code":"W22170112.A0","spec":"改制临工测试 B+B-电源线2米长安德森插头","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"旋转变压器","code":"T47210801.A1","spec":"J52XU9734-L49","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"0型密封圈","code":"T27080017.A0","spec":"JB7757.2(20*2)","material":"NBR70","weight_kg":None,"process":"","qty":2},
    {"name":"电控外壳","code":"J11160008.A0","spec":"ADC12 HPD","material":"","weight_kg":4.3,"process":"高压模具","qty":1},
    {"name":"特大垫圈C级","code":"T19030302.A1","spec":"GB/T 5287-2002（5/镀白锌）","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"吊耳","code":"T46170061.A1","spec":"304不锈钢","material":"","weight_kg":None,"process":"","qty":2},
    {"name":"定子总成","code":"T44001177","spec":"OD220定子总成（028）","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"定子组件","code":"T44200282.A0","spec":"OD220mm，L135mm浸漆定子组件","material":"扁线4.12*1.92","weight_kg":5.6,"process":"","qty":1},
    {"name":"定子铁芯","code":"T44210291.A1","spec":"OD220mm，L135mm，三V","material":"B30AHV1500","weight_kg":14.3,"process":"","qty":1},
    {"name":"机壳","code":"T44100282.A0","spec":"拉伸机壳OD220mm，L243mm","material":"6063-T5","weight_kg":9.49,"process":"","qty":1},
    {"name":"转子总成","code":"T45001148","spec":"OD220转子总成（028）","material":"","weight_kg":None,"process":"","qty":1},
    {"name":"转子铁芯","code":"T45120291.A1","spec":"OD220mm，L22.7mm，三V","material":"B30AHV1500","weight_kg":2.03,"process":"","qty":6},
    {"name":"电机轴","code":"T45110282.A0","spec":"L=279.8mm，20CrMnTiH","material":"20CrMnTiH","weight_kg":2.78,"process":"","qty":1},
    {"name":"永磁体","code":"T45130291.A1","spec":"24×3.5×22.7mm","material":"48UH","weight_kg":0.014583333,"process":"","qty":96},
    {"name":"永磁体","code":"T45130292.A1","spec":"18×3×22.7mm","material":"48UH","weight_kg":0.009375,"process":"","qty":96},
    {"name":"永磁体","code":"T45130293.A1","spec":"9.7×3×22.7mm","material":"48UH","weight_kg":0.005052083,"process":"","qty":96},
    {"name":"转子挡板","code":"T45140281.A0","spec":"内外径50×159mm","material":"6061-T6","weight_kg":0.44,"process":"","qty":2},
    {"name":"转子轴套","code":"T45150291.A1","spec":"内外径50×82mm","material":"40Cr","weight_kg":0.28,"process":"","qty":1},
    {"name":"金属水嘴","code":"J19160007.A0","spec":"D20×1.5mm","material":"不锈钢","weight_kg":0.35,"process":"","qty":2},
    {"name":"橡胶软管","code":"W27010001.A0","spec":"19x27mm EPDM","material":"","weight_kg":0.04,"process":"","qty":0.14},
    {"name":"弹簧管卡","code":"W19010001.A0","spec":"锰钢，WN27","material":"","weight_kg":0.02,"process":"","qty":2},
    {"name":"内六角平圆头螺钉","code":"T19020703.A0","spec":"GB/T 70.2—2000 （M5x16 8.8级/达克罗）","material":"","weight_kg":None,"process":"","qty":1},
]

svc = FinanceSkillQuoteService(ai_route_service=FakeAIRouteService())

volumes = [1000, 5000, 10000, 50000]
results_by_volume = {}

for av in volumes:
    print(f"\n>>> Running annual_volume={av} ...", flush=True)
    try:
        result = svc.quote_items(items, model={"production_mode":"mass", "annual_volume": av, "label": "test"})
        rows = []
        for it in result.get("items", []):
            rows.append({
                "name": it.get("name"),
                "code": it.get("code"),
                "ai_route_unit_price": it.get("ai_route_unit_price"),
                "volume_baseline_unit_price": it.get("volume_baseline_unit_price"),
                "volume_conservative_unit_price": it.get("volume_conservative_unit_price"),
                "volume_aggressive_unit_price": it.get("volume_aggressive_unit_price"),
                "volume_pricing_summary": str(it.get("volume_pricing_summary") or "")[:80],
                "tooling_cost": it.get("tooling_cost"),
                "mass_break_even_volume": it.get("mass_break_even_volume"),
                "mass_process_route": it.get("mass_process_route"),
            })
        results_by_volume[av] = rows
        print(f"    Done, {len(rows)} items")
    except Exception as e:
        print(f"    ERROR: {e}")
        import traceback
        traceback.print_exc()

# 对比：找出量产越多单价越高的条目
print("\n\n=== 量产越多单价越高的条目（基于 volume_conservative_unit_price）===")
all_codes = {r["code"] for r in results_by_volume.get(volumes[0], [])}
for code in sorted(all_codes):
    vals = {}
    for av in volumes:
        for r in results_by_volume.get(av, []):
            if r["code"] == code:
                vals[av] = r["volume_conservative_unit_price"] or r["ai_route_unit_price"] or 0
                break
    if not vals:
        continue
    prices = [vals.get(av, 0) for av in volumes]
    # 检查是否单调递增
    if any(prices[i] > prices[i+1] for i in range(len(prices)-1)):
        continue  # 有下降，正常
    if any(prices[i] < prices[i+1] for i in range(len(prices)-1)):
        name = ""
        for r in results_by_volume.get(volumes[0], []):
            if r["code"] == code:
                name = r["name"]
                break
        print(f"  {name} ({code}): " + " -> ".join(f"{av}:{vals.get(av,0):.4f}" for av in volumes))

print("\n=== 完整对比表（量产口径）===")
for av in volumes:
    print(f"\n--- annual_volume={av} ---")
    for r in results_by_volume.get(av, []):
        print(f"  {r['name']}: ai={r['ai_route_unit_price']}, base={r['volume_baseline_unit_price']}, cons={r['volume_conservative_unit_price']}, aggr={r['volume_aggressive_unit_price']}, tooling={r['tooling_cost']}, route={r['mass_process_route']}")
