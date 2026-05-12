from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP_WEB_ROOT = ROOT / "app_web"
for candidate in (ROOT, APP_WEB_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app_web.backend.services.finance_skill_quote_service import FinanceSkillQuoteService


class FinancePricingSpecificItemsTests(unittest.TestCase):
    def test_large_b30ahv1500_dual_v_stator_core_locked_price_gets_uplifted(self):
        adjusted_price, reason = FinanceSkillQuoteService._resolve_stator_core_locked_price({
            "name": "定子铁芯",
            "spec": "OD200mm，B30AHV1500，L130mm，双V",
            "material": "无取向硅钢片 (B30AHV1500)",
            "process": "硅钢片冲压与叠压固化",
            "weight_kg": 12.915,
            "changjiang_route_unit_price": 149.1683,
        })

        self.assertGreaterEqual(
            adjusted_price,
            260.0,
            "B30AHV1500 + OD200 + L130 + 双V 的大规格定子铁芯，不应继续锁死在过低的 skills 规则价上",
        )
        self.assertIn("B30AHV1500", reason)
        self.assertIn("双V", reason)

    def test_stator_core_enters_mass_tooling_route_with_stamping_die_break_even(self):
        mass_quote = FinanceSkillQuoteService._resolve_stator_core_mass_production_quote({
            "name": "定子铁芯",
            "spec": "OD180mm，L90mm，V+1",
            "material": "电工钢（硅钢片）",
            "process": "冲压叠压",
            "weight_kg": 7.37,
            "annual_volume": 10000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertGreater(float(mass_quote.get("mass_tooling_unit_price") or 0), 0)
        self.assertEqual(mass_quote.get("mass_process_route"), "冲压模+叠压")
        self.assertIn("量产口径", str(mass_quote.get("volume_pricing_summary") or ""))
        self.assertIn("开模费", str(mass_quote.get("note") or ""))
        self.assertIn("冲压模", str(mass_quote.get("note") or ""))

    def test_rotor_core_enters_mass_tooling_route_with_stamping_die_break_even(self):
        mass_quote = FinanceSkillQuoteService._resolve_stator_core_mass_production_quote({
            "name": "转子铁芯",
            "spec": "OD180mm，L30mm，V+1",
            "material": "无取向硅钢片",
            "process": "冲压成型、叠压铆接",
            "weight_kg": 1.57,
            "annual_volume": 10000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertGreater(float(mass_quote.get("mass_tooling_unit_price") or 0), 0)
        self.assertEqual(mass_quote.get("mass_process_route"), "冲压模+叠压")
        self.assertIn("量产口径", str(mass_quote.get("volume_pricing_summary") or ""))
        self.assertIn("开模费", str(mass_quote.get("note") or ""))
        self.assertIn("冲压模", str(mass_quote.get("note") or ""))

    def test_stator_assembly_still_does_not_enter_core_mass_tooling_route(self):
        self.assertEqual(
            FinanceSkillQuoteService._resolve_stator_core_mass_production_quote({
                "name": "定子组件",
                "spec": "OD180mm，L90mm浸漆定子组件",
                "material": "硅钢片+漆包线",
                "process": "自动嵌线、真空压力浸漆",
                "weight_kg": 2.1735,
                "annual_volume": 10000,
            }),
            {},
            "定子组件不是铁芯冲压叠压件，不应进入铁芯量产模具口径",
        )

    def test_stator_winding_component_recognizes_stator_assembly_with_vpi_process(self):
        self.assertTrue(
            FinanceSkillQuoteService._is_stator_winding_component({
                "name": "定子总成",
                "spec": "OD220定子总成（028）",
                "material": "铜",
                "process": "冲片叠压、线圈嵌线、真空压力浸漆 (VPI) 及烘干",
            }),
            "定子总成如果已经明确带嵌线+VPI，应视作定子绕组/总成类对象，而不是普通未识别物料",
        )

    def test_stator_winding_component_recognizes_stator_assembly_even_with_coarse_process_text(self):
        self.assertTrue(
            FinanceSkillQuoteService._is_stator_winding_component({
                "name": "定子总成",
                "spec": "OD220电机定子总成",
                "material": "硅钢片、绝缘材料",
                "process": "叠压装配",
            }),
            "只要名称已明确是定子总成，就不应因为工艺文本较粗而漏掉总成类报价路线",
        )

    def test_stator_core_component_does_not_misclassify_stator_assembly_as_core(self):
        self.assertFalse(
            FinanceSkillQuoteService._is_stator_core_component({
                "name": "定子总成",
                "spec": "OD220定子总成，含铁芯",
                "material": "硅钢片",
                "process": "叠压装配",
            }),
            "定子总成即便文本里出现铁芯/硅钢，也不应误落到裸铁芯报价路线",
        )

    def test_stator_assembly_enters_mass_tooling_route_with_winding_fixture_break_even(self):
        mass_quote = FinanceSkillQuoteService._resolve_stator_winding_mass_production_quote({
            "name": "定子总成",
            "spec": "OD220定子总成（028）",
            "material": "铜",
            "process": "冲片叠压、线圈嵌线、真空压力浸漆 (VPI) 及烘干",
            "weight_kg": 5.6,
            "changjiang_route_unit_price": 1136.038,
            "ai_route_unit_price": 1136.038,
            "annual_volume": 3000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertGreater(float(mass_quote.get("mass_tooling_unit_price") or 0), 0)
        self.assertEqual(mass_quote.get("mass_process_route"), "绕线工装+嵌线/VPI治具")
        self.assertIn("量产口径", str(mass_quote.get("volume_pricing_summary") or ""))
        self.assertIn("开模费", str(mass_quote.get("note") or ""))
        self.assertIn("VPI", str(mass_quote.get("note") or ""))
        self.assertLess(
            float(mass_quote.get("mass_tooling_unit_price") or 0),
            1136.038,
            "3000套/年的定子总成命中量产工装化路线后，当前单价应低于样品/小批口径",
        )

    def test_stator_round_wire_is_default_and_costs_more_than_flat_wire(self):
        round_quote = FinanceSkillQuoteService._resolve_stator_winding_mass_production_quote({
            "name": "定子组件",
            "spec": "OD220定子组件",
            "material": "硅钢片、铜线、绝缘材料",
            "process": "绕线、嵌线、浸漆",
            "weight_kg": 5.6,
            "annual_volume": 3000,
            "ai_route_unit_price": 1136.038,
        })
        flat_quote = FinanceSkillQuoteService._resolve_stator_winding_mass_production_quote({
            "name": "定子组件",
            "spec": "OD220扁线定子组件",
            "material": "硅钢片、扁铜线、绝缘材料",
            "process": "绕线、嵌线、浸漆",
            "weight_kg": 5.6,
            "annual_volume": 3000,
            "ai_route_unit_price": 1136.038,
        })
        default_quote = FinanceSkillQuoteService._resolve_stator_winding_mass_production_quote({
            "name": "定子组件",
            "spec": "OD220定子组件",
            "material": "硅钢片、绝缘材料",
            "process": "绕线、嵌线、浸漆",
            "weight_kg": 5.6,
            "annual_volume": 3000,
            "ai_route_unit_price": 1136.038,
        })

        self.assertGreater(float(round_quote.get("unit_price") or 0), float(flat_quote.get("unit_price") or 0))
        self.assertEqual(default_quote.get("wire_variant"), "round")
        self.assertIn("圆线", str(round_quote.get("note") or ""))
        self.assertIn("扁线", str(flat_quote.get("note") or ""))

    def test_rotor_assembly_enters_mass_tooling_route_with_balance_and_magnet_processes(self):
        mass_quote = FinanceSkillQuoteService._resolve_rotor_assembly_mass_production_quote({
            "name": "转子总成",
            "spec": "OD220转子总成（028）",
            "material": "硅钢片、钕铁硼磁钢、45#钢轴",
            "process": "冲压叠压、铸铝/嵌铜、磁钢装配、动平衡校正",
            "weight_kg": 10.5,
            "annual_volume": 5000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertGreater(float(mass_quote.get("mass_tooling_unit_price") or 0), 0)
        self.assertEqual(mass_quote.get("mass_process_route"), "转子压铸/嵌铜+磁钢装配治具")
        self.assertIn("量产口径", str(mass_quote.get("volume_pricing_summary") or ""))
        self.assertIn("开模费", str(mass_quote.get("note") or ""))
        self.assertIn("动平衡", str(mass_quote.get("note") or ""))

    def test_rotor_assembly_recognizes_name_only_total_assembly_with_coarse_process_text(self):
        self.assertTrue(
            FinanceSkillQuoteService._is_rotor_assembly_component({
                "name": "转子总成",
                "spec": "OD220高速油泵转子总成",
                "material": "硅钢片、钢轴",
                "process": "总成装配",
            }),
            "转子总成不应因为工艺文本缺少磁钢/动平衡关键词就整体漏掉转子总成报价路线",
        )

    def test_rotor_assembly_mass_quote_works_with_name_only_total_assembly(self):
        mass_quote = FinanceSkillQuoteService._resolve_rotor_assembly_mass_production_quote({
            "name": "转子总成",
            "spec": "OD220高速油泵转子总成",
            "material": "硅钢片、钢轴",
            "process": "总成装配",
            "weight_kg": 10.5,
            "annual_volume": 3000,
        })

        self.assertGreater(float(mass_quote.get("mass_tooling_unit_price") or 0), 0)
        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertIn("转子总成", str(mass_quote.get("note") or ""))

    def test_large_stretched_housing_formula_includes_default_post_processing_cost(self):
        quote = FinanceSkillQuoteService._resolve_precision_housing_formula_quote({
            "name": "机壳",
            "spec": "拉伸机壳OD200mm，L213mm",
            "material": "铝合金",
            "process": "金属板材深拉伸成型",
            "weight_kg": 5.6,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            220.0,
            "OD200/L213/5.6kg 的大规格拉伸机壳不应只按裸拉伸成形估价，至少要带上默认后续机加工和表处成本",
        )
        self.assertIn("后续机加工", str(quote.get("note") or ""))

    def test_large_stretched_housing_enters_mass_tooling_route(self):
        mass_quote = FinanceSkillQuoteService._resolve_precision_housing_mass_production_quote({
            "name": "机壳",
            "spec": "拉伸机壳OD180mm，L168mm",
            "material": "低碳钢（SPCC）",
            "process": "金属板材深拉伸成型",
            "weight_kg": 3.3,
            "annual_volume": 10000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertIn("开模费", str(mass_quote.get("note") or ""))

    def test_long_20crmnti_motor_shaft_formula_covers_heat_treatment_and_grinding(self):
        quote = FinanceSkillQuoteService._resolve_precision_shaft_formula_quote({
            "name": "电机轴",
            "spec": "L334mm，花键轴",
            "material": "20CrMnTi 合金结构钢",
            "process": "锻造下料、粗车、渗碳淬火、精车、外圆磨、花键铣",
            "weight_kg": 5.8,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            700.0,
            "L334 的 20CrMnTi 电机轴如果包含渗碳淬火、外圆磨和花键，不应继续停留在三四百元低位",
        )
        self.assertIn("渗碳淬火", str(quote.get("note") or ""))
        self.assertIn("外圆磨", str(quote.get("note") or ""))

    def test_precision_shaft_mass_quote_uses_tooling_unit_price_and_tracks_break_even(self):
        sample_quote = FinanceSkillQuoteService._resolve_precision_shaft_formula_quote({
            "name": "电机轴",
            "spec": "L334mm，花键轴",
            "material": "20CrMnTi 合金结构钢",
            "process": "锻造下料、粗车、渗碳淬火、精车、外圆磨、花键铣",
            "weight_kg": 5.8,
        })
        mass_quote = FinanceSkillQuoteService._resolve_precision_shaft_mass_production_quote({
            "name": "电机轴",
            "spec": "L334mm，花键轴",
            "material": "20CrMnTi 合金结构钢",
            "process": "锻造下料、粗车、渗碳淬火、精车、外圆磨、花键铣",
            "weight_kg": 5.8,
            "annual_volume": 10000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        sample_unit = float(sample_quote.get("price") or 0)
        mass_unit = float(mass_quote.get("unit_price") or 0)
        self.assertLess(
            mass_unit,
            sample_unit,
            "量产开模单价应明显低于样品/小批量机加工单价，但开模费需单独展示而不是并入当前单价",
        )
        self.assertLessEqual(
            mass_unit,
            sample_unit * 0.4,
            "高精轴量产开模后单价应显著低于样品机加工价，目标至少压到 4 折以内",
        )
        self.assertIn("开模费", str(mass_quote.get("note") or ""))
        self.assertIn("划算", str(mass_quote.get("note") or ""))

    def test_large_35mm2_harness_formula_counts_multi_branch_copper_and_termination(self):
        quote = FinanceSkillQuoteService._resolve_motor_harness_formula_quote({
            "name": "线束总成",
            "spec": "35mm²，L=1.8m/1.6m/1.5m，3分支，含铜鼻子、护套、热缩管",
            "material": "铜+PVC",
            "process": "裁线、压接端子、分支包扎、装配",
            "weight_kg": 1.25,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            140.0,
            "35mm² 多段多分支线束不能只按轻小件重量估价，至少要体现铜耗、端子压接和装配成本",
        )
        self.assertIn("35mm²", str(quote.get("note") or ""))
        self.assertIn("压接端子", str(quote.get("note") or ""))

    def test_harness_formula_treats_700_710_800_as_mm_not_meters(self):
        quote = FinanceSkillQuoteService._resolve_motor_harness_formula_quote({
            "name": "线束总成",
            "spec": "线径35mm²，线长700mm，710mm，800mm",
            "material": "无氧铜导体，交联聚烯烃或硅胶绝缘层",
            "process": "线缆裁切、剥皮、端子压接、护套组装",
            "weight_kg": 0.45,
        })

        self.assertGreater(float(quote.get("price") or 0), 80.0)
        self.assertLess(float(quote.get("price") or 0), 500.0)
        self.assertIn("总长 2.21m", str(quote.get("note") or ""))

    def test_precision_front_end_cover_formula_counts_lpdc_cnc_and_sealing(self):
        quote = FinanceSkillQuoteService._resolve_precision_end_cover_formula_quote({
            "name": "前端盖",
            "spec": "OD200mm前端盖，双20行驶，轴承室，止口，安装面，螺纹孔，密封槽",
            "material": "A356-T6",
            "process": "低压铸造、CNC、轴承室精加工、止口、安装面、螺纹孔、密封槽、喷涂",
            "weight_kg": 1.72,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            190.0,
            "OD200 的前端盖如果含轴承室、止口、螺纹孔和密封槽，不应只停在通用端盖低位估价",
        )
        self.assertIn("轴承室", str(quote.get("note") or ""))
        self.assertIn("密封槽", str(quote.get("note") or ""))

    def test_precision_rear_end_cover_formula_counts_heavier_structure_and_surface(self):
        quote = FinanceSkillQuoteService._resolve_precision_end_cover_formula_quote({
            "name": "后端盖",
            "spec": "OD200mm后端盖，轴承室，止口，安装面，螺纹孔，密封槽",
            "material": "A356-T6",
            "process": "低压铸造、CNC、轴承室精加工、止口、安装面、螺纹孔、密封槽、喷涂",
            "weight_kg": 1.9,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            250.0,
            "OD200 的后端盖通常比前端盖更重、结构更复杂，不应继续压在一百多元区间",
        )
        self.assertIn("喷涂", str(quote.get("note") or ""))

    def test_precision_end_cover_mass_quote_shows_tooling_without_adding_it_to_unit_price(self):
        sample_quote = FinanceSkillQuoteService._resolve_precision_end_cover_formula_quote({
            "name": "后端盖",
            "spec": "OD200mm后端盖，轴承室，止口，安装面，螺纹孔，密封槽",
            "material": "A356-T6",
            "process": "低压铸造、CNC、轴承室精加工、止口、安装面、螺纹孔、密封槽、喷涂",
            "weight_kg": 1.9,
        })
        mass_quote = FinanceSkillQuoteService._resolve_precision_end_cover_mass_production_quote({
            "name": "后端盖",
            "spec": "OD200mm后端盖，轴承室，止口，安装面，螺纹孔，密封槽",
            "material": "A356-T6",
            "process": "低压铸造、CNC、轴承室精加工、止口、安装面、螺纹孔、密封槽、喷涂",
            "weight_kg": 1.9,
            "annual_volume": 10000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        sample_unit = float(sample_quote.get("price") or 0)
        mass_unit = float(mass_quote.get("unit_price") or 0)
        self.assertLess(mass_unit, sample_unit)
        self.assertLessEqual(
            mass_unit,
            sample_unit * 0.55,
            "端盖量产开模单价应显著低于样品机加工价，至少应压到 55% 以内",
        )
        self.assertIn("开模费", str(mass_quote.get("note") or ""))

    def test_front_end_cover_with_sparse_features_still_enters_mass_tooling_route(self):
        item = {
            "code": "T46111198",
            "name": "前端盖",
            "spec": "OD200mm前端盖（双20行驶）",
            "material": "",
            "process": "低压铸造",
            "weight_kg": 0.0,
            "annual_volume": 10000,
        }
        sample_quote = FinanceSkillQuoteService._resolve_precision_end_cover_formula_quote(item)
        mass_quote = FinanceSkillQuoteService._resolve_precision_end_cover_mass_production_quote(item)

        self.assertGreater(
            float(sample_quote.get("price") or 0),
            0,
            "像前端盖这类名称和规格已经很明确的精密端盖，即使没补齐材质/重量，也应走端盖样品机加工公式的默认口径",
        )
        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertLess(
            float(mass_quote.get("unit_price") or 0),
            float(sample_quote.get("price") or 0) * 0.55,
            "像前端盖这类输入特征偏弱但业务上明确属于精密端盖的件，也应默认进入量产开模口径，且开模价应显著低于机加工价",
        )

    def test_large_metal_rotor_baffle_defaults_into_mass_tooling_route(self):
        item = {
            "name": "转子挡板",
            "spec": "内外径45×117mm，钢制挡板",
            "material": "45#钢",
            "process": "冲压成型",
            "weight_kg": 0.144,
            "annual_volume": 10000,
        }
        mass_quote = FinanceSkillQuoteService._resolve_motor_shell_mass_production_quote(item)

        self.assertGreater(
            float(mass_quote.get("tooling_cost") or 0),
            0,
            "像转子挡板这类大金属结构件，虽不属于端盖/壳体，也应默认纳入量产开模口径",
        )
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertIn("开模费", str(mass_quote.get("note") or ""))

    def test_metal_bearing_cover_defaults_into_mass_tooling_route(self):
        item = {
            "name": "轴承压盖",
            "spec": "内外径42×95mm",
            "material": "铝合金 ADC12",
            "process": "铝合金压铸",
            "weight_kg": 0.21,
            "annual_volume": 10000,
        }
        mass_quote = FinanceSkillQuoteService._resolve_motor_shell_mass_production_quote(item)

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertIn("开模费", str(mass_quote.get("note") or ""))

    def test_terminal_box_enters_mass_tooling_route(self):
        item = {
            "name": "接线盒",
            "spec": "123×70×56mm",
            "material": "ADC12",
            "process": "高压铸造",
            "weight_kg": 0.581,
            "annual_volume": 10000,
            "product_spec": "柳工3.5T双20行走电机总成",
        }
        mass_quote = FinanceSkillQuoteService._resolve_motor_shell_mass_production_quote(item)

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertGreater(float(mass_quote.get("unit_price") or 0), 0)
        self.assertIn("接线盒", str(mass_quote.get("note") or ""))
        self.assertIn("开模费", str(mass_quote.get("note") or ""))

    def test_small_rotor_bushing_also_enters_mass_tooling_route(self):
        item = {
            "name": "转子轴套",
            "spec": "内外径45*57mm",
            "material": "45钢",
            "process": "机加工",
            "weight_kg": 0.075,
            "annual_volume": 10000,
        }
        mass_quote = FinanceSkillQuoteService._resolve_motor_shell_mass_production_quote(item)

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        self.assertGreater(float(mass_quote.get("unit_price") or 0), 0)
        self.assertIn("轴套", str(mass_quote.get("note") or ""))
        self.assertIn("开模费", str(mass_quote.get("note") or ""))

    def test_stator_assembly_does_not_enter_mass_tooling_route(self):
        item = {
            "name": "定子组件",
            "spec": "OD180mm，L90mm浸漆定子组件",
            "material": "硅钢片+漆包线",
            "process": "自动嵌线、真空压力浸漆",
            "weight_kg": 2.1735,
            "annual_volume": 10000,
        }
        self.assertEqual(
            FinanceSkillQuoteService._resolve_motor_shell_mass_production_quote(item),
            {},
            "定子组件属于绕组/浸漆成品组件，不应被默认纳入开模口径",
        )

    def test_small_screw_does_not_enter_mass_tooling_route(self):
        item = {
            "name": "内六角圆柱头螺钉",
            "spec": "M5x16/8.8级/达克罗",
            "material": "中碳钢",
            "process": "冷镦成型、滚丝、热处理、达克罗",
            "weight_kg": 0.02,
            "annual_volume": 10000,
        }
        self.assertEqual(
            FinanceSkillQuoteService._resolve_motor_shell_mass_production_quote(item),
            {},
            "螺丝这类小金属标准件不应进入量产开模口径",
        )

    def test_motor_shell_mass_quote_shows_tooling_without_adding_it_to_unit_price(self):
        sample_quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            "name": "接线盒",
            "spec": "ADC12 接线盒成品，OD176mm，4孔",
            "material": "压铸铝合金 ADC12",
            "process": "高压压铸、CNC、钻孔攻丝、喷涂",
            "weight_kg": 1.85,
        })
        mass_quote = FinanceSkillQuoteService._resolve_motor_shell_mass_production_quote({
            "name": "接线盒",
            "spec": "ADC12 接线盒成品，OD176mm，4孔",
            "material": "压铸铝合金 ADC12",
            "process": "高压压铸、CNC、钻孔攻丝、喷涂",
            "weight_kg": 1.85,
            "annual_volume": 10000,
        })

        self.assertGreater(float(mass_quote.get("tooling_cost") or 0), 0)
        self.assertGreater(float(mass_quote.get("break_even_volume") or 0), 0)
        sample_unit = float(sample_quote.get("price") or 0)
        mass_unit = float(mass_quote.get("unit_price") or 0)
        self.assertLess(mass_unit, sample_unit)
        self.assertLessEqual(
            mass_unit,
            sample_unit * 0.6,
            "壳体/接线盒量产开模单价应显著低于样品机加工价，至少应压到 6 折以内",
        )
        self.assertIn("开模费", str(mass_quote.get("note") or ""))

    def test_die_cast_terminal_box_finished_part_counts_casting_machining_and_surface(self):
        quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            "name": "接线盒",
            "spec": "ADC12 接线盒成品，OD176mm，4孔",
            "material": "压铸铝合金 ADC12",
            "process": "高压压铸、CNC、钻孔攻丝、喷涂",
            "weight_kg": 1.85,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            180.0,
            "ADC12 接线盒成品不应只按一般铝件件价，应体现压铸、机加和喷涂",
        )
        self.assertIn("压铸", str(quote.get("note") or ""))
        self.assertIn("喷涂", str(quote.get("note") or ""))

    def test_simple_adc12_terminal_box_casting_only_stays_near_40(self):
        quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            "name": "接线盒",
            "spec": "123×70×56mm",
            "material": "铝ADC12",
            "process": "高压铸造",
            "weight_kg": 0.58,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            35.0,
            "仅有高压铸造信息的小型 ADC12 接线盒，不应被压得过低到脱离材料+压铸基本成本",
        )
        self.assertLessEqual(
            float(quote.get("price") or 0),
            50.0,
            "仅有高压铸造信息的小型 ADC12 接线盒，不应默认叠加完整机加工和表处，目标应回到 40 左右",
        )

    def test_terminal_box_product_spec_context_can_upgrade_blank_to_finished_like_quote(self):
        base_item = {
            "name": "接线盒",
            "spec": "123×70×56mm",
            "material": "铝ADC12",
            "process": "高压铸造",
            "weight_kg": 0.58,
        }
        base_quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote(base_item)
        enriched_quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            **base_item,
            "product_spec": "200机座号永磁电机平台，接线盒成品，需机加工攻丝喷涂",
        })

        self.assertGreater(
            float(enriched_quote.get("price") or 0),
            float(base_quote.get("price") or 0),
            "如果补入产品规格上下文能明确接线盒属于成品并需机加工喷涂，报价应高于仅凭自身简略规格时的估价",
        )
        self.assertIn("喷涂", str(enriched_quote.get("note") or ""))

    def test_die_cast_terminal_box_blank_does_not_get_finished_part_costs(self):
        quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            "name": "接线盒",
            "spec": "ADC12 接线盒毛坯，OD176mm，4孔",
            "material": "压铸铝合金 ADC12",
            "process": "高压压铸毛坯",
            "weight_kg": 1.85,
        })

        self.assertLessEqual(
            float(quote.get("price") or 0),
            120.0,
            "接线盒毛坯不应被算入完整机加工和表处成本，否则会把毛坯价误抬成成品价",
        )
        self.assertIn("毛坯", str(quote.get("note") or ""))

    def test_simple_rear_cover_plate_casting_only_stays_out_of_finished_part_zone(self):
        quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            "name": "后盖板",
            "spec": "ADC12 后盖板 120×80mm",
            "material": "铝ADC12",
            "process": "高压铸造",
            "weight_kg": 0.42,
        })

        self.assertGreaterEqual(float(quote.get("price") or 0), 30.0)
        self.assertLessEqual(
            float(quote.get("price") or 0),
            55.0,
            "仅有压铸信息的小型后盖板，不应默认叠加完整机加工和表处而被高估到八九十元",
        )

    def test_simple_three_phase_cover_plate_casting_only_stays_out_of_finished_part_zone(self):
        quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            "name": "三相盖板",
            "spec": "ADC12 三相盖板 120×90mm",
            "material": "铝ADC12",
            "process": "高压铸造",
            "weight_kg": 0.46,
        })

        self.assertGreaterEqual(float(quote.get("price") or 0), 30.0)
        self.assertLessEqual(
            float(quote.get("price") or 0),
            55.0,
            "仅有压铸信息的小型三相盖板，不应默认叠加完整机加工和表处而被高估到八九十元",
        )

    def test_three_phase_cover_plate_formula_counts_casting_finish_machining_and_hole_features(self):
        quote = FinanceSkillQuoteService._resolve_motor_shell_formula_quote({
            "name": "三相盖板",
            "spec": "QT450-10，外径190mm，6孔，止口",
            "material": "球墨铸铁 QT450-10",
            "process": "铸造、机加工、钻孔攻丝、喷粉",
            "weight_kg": 2.4,
        })

        self.assertGreaterEqual(
            float(quote.get("price") or 0),
            180.0,
            "QT450-10 的三相盖板应体现铸造毛坯、机加、孔位和表处，不应被压回通用小盖板价",
        )
        self.assertIn("QT450-10", str(quote.get("note") or ""))
        self.assertIn("6孔", str(quote.get("note") or ""))
        self.assertIn("喷粉", str(quote.get("note") or ""))


if __name__ == "__main__":
    unittest.main()
