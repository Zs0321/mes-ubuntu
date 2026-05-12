"""
AI报价系统 - 零部件成本计算引擎
支持不同类型零部件的经验公式计算
"""

import json
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path
import math


@dataclass
class CostBreakdown:
    """成本分解结果"""
    material_cost: float       # 材料成本
    processing_cost: float     # 加工成本
    tooling_cost: float        # 模具分摊
    overhead_cost: float       # 管理费用
    total_cost: float          # 总成本
    details: Dict = field(default_factory=dict)  # 详细信息


class ComponentCostCalculator(ABC):
    """零部件成本计算器基类"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.load_default_params()
    
    @abstractmethod
    def load_default_params(self):
        """加载默认参数"""
        pass
    
    @abstractmethod
    def calculate(self, **params) -> CostBreakdown:
        """计算成本"""
        pass
    
    def update_params(self, params: Dict):
        """更新计算参数"""
        self.config.update(params)


# ============================================================
# 铝制品成本计算器
# ============================================================

class AluminumCastingCalculator(ComponentCostCalculator):
    """
    铝压铸件成本计算器
    
    主要影响因素:
    - 毛坯重量
    - 材料牌号(ADC12, A380等)
    - 加工复杂度
    - 表面处理
    - 批量
    """
    
    def load_default_params(self):
        self.config.setdefault('material_prices', {
            'ADC12': 22.0,      # 元/kg
            'A380': 24.0,
            'AlSi9Cu3': 25.0,
            'AlSi12': 23.0,
        })
        self.config.setdefault('casting_fee', 8.0)      # 压铸加工费 元/kg
        self.config.setdefault('machining_rate', 80.0)  # 机加工费率 元/小时
        self.config.setdefault('surface_treatment', {
            '无': 0,
            '喷粉': 15.0,       # 元/平方米
            '阳极氧化': 30.0,
            '电泳': 25.0,
            '喷漆': 20.0,
        })
        self.config.setdefault('tooling_life', 100000)  # 模具寿命(件)
        self.config.setdefault('overhead_rate', 0.08)   # 管理费率
    
    def calculate(
        self,
        weight_kg: float,
        material: str = 'ADC12',
        machining_hours: float = 0,
        surface_treatment: str = '无',
        surface_area_m2: float = 0,
        tooling_cost_total: float = 0,
        quantity: int = 1,
        scrap_rate: float = 0.03,
        **kwargs
    ) -> CostBreakdown:
        """
        计算铝压铸件成本
        
        Args:
            weight_kg: 零件净重(kg)
            material: 材料牌号
            machining_hours: 机加工工时
            surface_treatment: 表面处理方式
            surface_area_m2: 表面积(平方米)
            tooling_cost_total: 模具总成本
            quantity: 批量
            scrap_rate: 废品率
        """
        # 1. 材料成本 (含废品损耗)
        material_price = self.config['material_prices'].get(material, 22.0)
        gross_weight = weight_kg * (1 + scrap_rate + 0.15)  # 毛坯重量约为净重1.15-1.2倍
        material_cost = gross_weight * material_price
        
        # 2. 压铸加工费
        casting_cost = gross_weight * self.config['casting_fee']
        
        # 3. 机加工费
        machining_cost = machining_hours * self.config['machining_rate']
        
        # 4. 表面处理费
        surface_cost = 0
        if surface_treatment != '无' and surface_area_m2 > 0:
            surface_rate = self.config['surface_treatment'].get(surface_treatment, 0)
            surface_cost = surface_area_m2 * surface_rate
        
        processing_cost = casting_cost + machining_cost + surface_cost
        
        # 5. 模具分摊
        tooling_cost = 0
        if tooling_cost_total > 0 and quantity > 0:
            tooling_cost = tooling_cost_total / min(quantity, self.config['tooling_life'])
        
        # 6. 管理费用
        subtotal = material_cost + processing_cost + tooling_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        total_cost = subtotal + overhead_cost
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=round(tooling_cost, 2),
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(total_cost, 2),
            details={
                'casting_cost': round(casting_cost, 2),
                'machining_cost': round(machining_cost, 2),
                'surface_cost': round(surface_cost, 2),
                'gross_weight': round(gross_weight, 3),
            }
        )


class AluminumMachiningCalculator(ComponentCostCalculator):
    """
    铝机加工件成本计算器
    
    主要影响因素:
    - 毛坯重量/体积
    - 加工复杂度
    - 精度要求
    - 表面粗糙度
    """
    
    def load_default_params(self):
        self.config.setdefault('material_prices', {
            '6061': 28.0,       # 元/kg
            '6063': 26.0,
            '7075': 45.0,
            '2024': 40.0,
            '5052': 25.0,
        })
        self.config.setdefault('machining_rates', {
            '简单': 60.0,       # 元/小时
            '中等': 80.0,
            '复杂': 120.0,
            '精密': 180.0,
        })
        self.config.setdefault('material_utilization', 0.6)  # 材料利用率
        self.config.setdefault('overhead_rate', 0.08)
    
    def calculate(
        self,
        weight_kg: float,
        material: str = '6061',
        complexity: str = '中等',
        machining_hours: float = 0,
        **kwargs
    ) -> CostBreakdown:
        """
        计算铝机加工件成本
        """
        # 材料成本 (考虑利用率)
        material_price = self.config['material_prices'].get(material, 28.0)
        utilization = self.config['material_utilization']
        gross_weight = weight_kg / utilization
        material_cost = gross_weight * material_price
        
        # 加工成本
        rate = self.config['machining_rates'].get(complexity, 80.0)
        # 如果未提供工时，按重量估算
        if machining_hours == 0:
            complexity_factor = {'简单': 0.5, '中等': 1.0, '复杂': 2.0, '精密': 3.0}
            machining_hours = weight_kg * complexity_factor.get(complexity, 1.0)
        
        processing_cost = machining_hours * rate
        
        # 管理费用
        subtotal = material_cost + processing_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=0,
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={
                'gross_weight': round(gross_weight, 3),
                'machining_hours': round(machining_hours, 2),
            }
        )


class AluminumExtrusionCalculator(ComponentCostCalculator):
    """
    铝拉伸/挤压件成本计算器
    
    主要影响因素:
    - 截面复杂度
    - 长度
    - 材料牌号
    - 后加工
    """
    
    def load_default_params(self):
        self.config.setdefault('base_price_per_kg', 25.0)  # 基础单价 元/kg
        self.config.setdefault('section_complexity_factor', {
            '简单': 1.0,
            '中等': 1.3,
            '复杂': 1.8,
        })
        self.config.setdefault('mold_cost_per_kg', 2.0)    # 模具分摊
        self.config.setdefault('cutting_fee', 0.5)          # 切割费 元/刀
        self.config.setdefault('overhead_rate', 0.08)
    
    def calculate(
        self,
        weight_kg: float,
        length_m: float = 1.0,
        section_complexity: str = '中等',
        cuts: int = 2,
        **kwargs
    ) -> CostBreakdown:
        """计算铝挤压件成本"""
        base_price = self.config['base_price_per_kg']
        factor = self.config['section_complexity_factor'].get(section_complexity, 1.0)
        
        material_cost = weight_kg * base_price * factor
        processing_cost = cuts * self.config['cutting_fee']
        tooling_cost = weight_kg * self.config['mold_cost_per_kg']
        
        subtotal = material_cost + processing_cost + tooling_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=round(tooling_cost, 2),
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={'length': length_m}
        )


# ============================================================
# 钢制品/冲压件成本计算器
# ============================================================

class StampingCalculator(ComponentCostCalculator):
    """
    冲压件成本计算器
    
    主要影响因素:
    - 材料(厚度、牌号)
    - 展开面积/重量
    - 工序数量
    - 模具复杂度
    - 批量
    """
    
    def load_default_params(self):
        self.config.setdefault('material_prices', {
            'SPCC': 6.5,        # 冷轧板 元/kg
            'SPCD': 7.0,
            'SECC': 8.5,        # 镀锌板
            'SUS304': 18.0,     # 不锈钢
            'SUS430': 12.0,
        })
        self.config.setdefault('stamping_fee_per_stroke', {
            '小型(<100T)': 0.03,    # 元/冲次
            '中型(100-300T)': 0.06,
            '大型(>300T)': 0.12,
        })
        self.config.setdefault('process_count_factor', {
            1: 1.0,
            2: 1.8,
            3: 2.5,
            4: 3.2,
            5: 4.0,
        })
        self.config.setdefault('tooling_life', 500000)     # 模具寿命
        self.config.setdefault('material_utilization', 0.75)  # 材料利用率
        self.config.setdefault('overhead_rate', 0.08)
    
    def calculate(
        self,
        weight_kg: float,
        material: str = 'SPCC',
        press_size: str = '中型(100-300T)',
        process_count: int = 3,
        tooling_cost_total: float = 0,
        quantity: int = 1000,
        **kwargs
    ) -> CostBreakdown:
        """
        计算冲压件成本
        
        Args:
            weight_kg: 零件净重
            material: 材料牌号
            press_size: 冲床规格
            process_count: 工序数量
            tooling_cost_total: 模具总成本
            quantity: 批量
        """
        # 材料成本
        material_price = self.config['material_prices'].get(material, 6.5)
        utilization = self.config['material_utilization']
        gross_weight = weight_kg / utilization
        material_cost = gross_weight * material_price
        
        # 冲压加工费
        fee_per_stroke = self.config['stamping_fee_per_stroke'].get(press_size, 0.06)
        process_factor = self.config['process_count_factor'].get(
            min(process_count, 5), 
            process_count * 0.8
        )
        processing_cost = fee_per_stroke * process_factor * 100  # 假设100冲次/件
        
        # 模具分摊
        tooling_cost = 0
        if tooling_cost_total > 0:
            tooling_cost = tooling_cost_total / min(quantity, self.config['tooling_life'])
        
        # 管理费用
        subtotal = material_cost + processing_cost + tooling_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=round(tooling_cost, 2),
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={
                'gross_weight': round(gross_weight, 3),
                'process_count': process_count,
            }
        )


class SiliconSteelCalculator(ComponentCostCalculator):
    """
    硅钢片(定子/转子铁芯)成本计算器
    
    主要影响因素:
    - 硅钢片牌号(影响铁损、价格)
    - 重量
    - 叠压工艺
    - 绝缘处理
    """
    
    def load_default_params(self):
        self.config.setdefault('material_prices', {
            '50W470': 9.0,      # 元/kg
            '50W600': 7.5,
            '50W800': 6.5,
            '35W300': 12.0,     # 高效硅钢
            '35W250': 15.0,
            '30Q130': 25.0,     # 高频硅钢
        })
        self.config.setdefault('stamping_fee', 3.0)        # 冲片费 元/kg
        self.config.setdefault('stacking_fee', 2.0)        # 叠压费 元/kg
        self.config.setdefault('insulation_fee', 1.5)      # 绝缘处理 元/kg
        self.config.setdefault('material_utilization', 0.65)
        self.config.setdefault('overhead_rate', 0.08)
    
    def calculate(
        self,
        weight_kg: float,
        material: str = '50W470',
        include_insulation: bool = True,
        **kwargs
    ) -> CostBreakdown:
        """计算硅钢片铁芯成本"""
        material_price = self.config['material_prices'].get(material, 9.0)
        utilization = self.config['material_utilization']
        gross_weight = weight_kg / utilization
        
        material_cost = gross_weight * material_price
        
        processing_cost = weight_kg * (
            self.config['stamping_fee'] + 
            self.config['stacking_fee']
        )
        if include_insulation:
            processing_cost += weight_kg * self.config['insulation_fee']
        
        subtotal = material_cost + processing_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=0,
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={'gross_weight': round(gross_weight, 3)}
        )


# ============================================================
# 电磁材料成本计算器
# ============================================================

class MagnetCalculator(ComponentCostCalculator):
    """
    磁钢成本计算器
    
    主要影响因素:
    - 磁钢牌号(N35, N42, N48等)
    - 重量
    - 形状复杂度
    - 表面处理(镀镍等)
    """
    
    def load_default_params(self):
        self.config.setdefault('material_prices', {
            'N35': 180.0,       # 元/kg
            'N38': 200.0,
            'N42': 250.0,
            'N45': 320.0,
            'N48': 400.0,
            'N52': 550.0,
            'N35SH': 280.0,     # 耐高温
            'N42SH': 350.0,
        })
        self.config.setdefault('processing_fee', 30.0)     # 加工费 元/kg
        self.config.setdefault('coating_fee', 15.0)        # 镀层费 元/kg
        self.config.setdefault('overhead_rate', 0.05)
    
    def calculate(
        self,
        weight_kg: float,
        grade: str = 'N42',
        with_coating: bool = True,
        **kwargs
    ) -> CostBreakdown:
        """计算磁钢成本"""
        material_price = self.config['material_prices'].get(grade, 250.0)
        material_cost = weight_kg * material_price
        
        processing_cost = weight_kg * self.config['processing_fee']
        if with_coating:
            processing_cost += weight_kg * self.config['coating_fee']
        
        subtotal = material_cost + processing_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=0,
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={'grade': grade}
        )


class CopperWindingCalculator(ComponentCostCalculator):
    """
    铜线绕组成本计算器
    
    主要影响因素:
    - 铜线重量
    - 线径
    - 绕线复杂度
    - 绝缘等级
    """
    
    def load_default_params(self):
        self.config.setdefault('copper_price', 72.0)       # 铜价 元/kg
        self.config.setdefault('enamel_premium', 8.0)      # 漆包线加价 元/kg
        self.config.setdefault('winding_rates', {
            '简单': 20.0,       # 绕线费 元/kg
            '中等': 35.0,
            '复杂': 55.0,
            '扁线': 80.0,       # 扁线绕组
        })
        self.config.setdefault('insulation_class_premium', {
            'B': 0,
            'F': 2.0,
            'H': 5.0,
        })
        self.config.setdefault('overhead_rate', 0.08)
    
    def calculate(
        self,
        weight_kg: float,
        winding_type: str = '中等',
        insulation_class: str = 'F',
        **kwargs
    ) -> CostBreakdown:
        """计算铜线绕组成本"""
        # 材料成本
        base_price = self.config['copper_price'] + self.config['enamel_premium']
        insulation_premium = self.config['insulation_class_premium'].get(insulation_class, 0)
        material_cost = weight_kg * (base_price + insulation_premium)
        
        # 绕线加工费
        winding_rate = self.config['winding_rates'].get(winding_type, 35.0)
        processing_cost = weight_kg * winding_rate
        
        subtotal = material_cost + processing_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=0,
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={'winding_type': winding_type}
        )


# ============================================================
# 机械部件成本计算器
# ============================================================

class ShaftCalculator(ComponentCostCalculator):
    """
    轴类零件成本计算器
    
    主要影响因素:
    - 材料(45钢、40Cr等)
    - 直径、长度
    - 加工复杂度
    - 热处理
    """
    
    def load_default_params(self):
        self.config.setdefault('material_prices', {
            '45钢': 5.5,        # 元/kg
            '40Cr': 7.0,
            '42CrMo': 9.0,
            '20CrMnTi': 8.5,
            'GCr15': 12.0,      # 轴承钢
        })
        self.config.setdefault('machining_rate', 100.0)    # 元/小时
        self.config.setdefault('heat_treatment', {
            '无': 0,
            '调质': 2.0,        # 元/kg
            '渗碳淬火': 5.0,
            '高频淬火': 3.5,
        })
        self.config.setdefault('overhead_rate', 0.08)
    
    def calculate(
        self,
        weight_kg: float,
        material: str = '45钢',
        machining_hours: float = 0,
        heat_treatment: str = '调质',
        diameter_mm: float = 50,
        length_mm: float = 200,
        **kwargs
    ) -> CostBreakdown:
        """计算轴类零件成本"""
        material_price = self.config['material_prices'].get(material, 5.5)
        
        # 毛坯重量 (直径放大10-15%)
        gross_diameter = diameter_mm * 1.12
        gross_length = length_mm + 10
        volume = math.pi * (gross_diameter/2000)**2 * (gross_length/1000)
        gross_weight = volume * 7850  # 钢密度 7850 kg/m³
        gross_weight = max(gross_weight, weight_kg * 1.3)
        
        material_cost = gross_weight * material_price
        
        # 加工成本 (按重量估算工时)
        if machining_hours == 0:
            machining_hours = weight_kg * 0.8  # 经验系数
        processing_cost = machining_hours * self.config['machining_rate']
        
        # 热处理
        ht_cost = self.config['heat_treatment'].get(heat_treatment, 0) * weight_kg
        processing_cost += ht_cost
        
        subtotal = material_cost + processing_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=0,
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={
                'gross_weight': round(gross_weight, 3),
                'heat_treatment': heat_treatment,
            }
        )


class BearingCalculator(ComponentCostCalculator):
    """
    轴承成本计算器
    采用标准件查表方式
    """
    
    def load_default_params(self):
        # 按内径范围的参考价格
        self.config.setdefault('price_by_bore', {
            (0, 20): 15.0,
            (20, 40): 25.0,
            (40, 60): 45.0,
            (60, 80): 70.0,
            (80, 100): 100.0,
            (100, 150): 180.0,
            (150, 200): 300.0,
        })
        self.config.setdefault('type_factor', {
            '深沟球': 1.0,
            '角接触球': 1.5,
            '圆柱滚子': 1.8,
            '圆锥滚子': 2.0,
            '调心滚子': 2.5,
        })
        self.config.setdefault('brand_factor', {
            '国产普通': 1.0,
            '国产优质': 1.5,
            'NSK': 2.5,
            'SKF': 3.0,
            'FAG': 2.8,
        })
    
    def calculate(
        self,
        bore_diameter_mm: float,
        bearing_type: str = '深沟球',
        brand: str = '国产优质',
        quantity: int = 2,
        **kwargs
    ) -> CostBreakdown:
        """计算轴承成本"""
        # 查找基础价格
        base_price = 50.0
        for (low, high), price in self.config['price_by_bore'].items():
            if low <= bore_diameter_mm < high:
                base_price = price
                break
        
        type_factor = self.config['type_factor'].get(bearing_type, 1.0)
        brand_factor = self.config['brand_factor'].get(brand, 1.0)
        
        unit_price = base_price * type_factor * brand_factor
        total_cost = unit_price * quantity
        
        return CostBreakdown(
            material_cost=round(total_cost, 2),
            processing_cost=0,
            tooling_cost=0,
            overhead_cost=0,
            total_cost=round(total_cost, 2),
            details={
                'unit_price': round(unit_price, 2),
                'quantity': quantity,
                'bearing_type': bearing_type,
            }
        )


# ============================================================
# 电子元器件成本计算器
# ============================================================

class PCBACalculator(ComponentCostCalculator):
    """
    PCBA成本计算器
    
    主要影响因素:
    - PCB层数、面积
    - 元器件BOM
    - SMT点数
    - 测试要求
    """
    
    def load_default_params(self):
        self.config.setdefault('pcb_price_per_dm2', {
            2: 3.0,             # 2层板 元/平方分米
            4: 6.0,
            6: 12.0,
            8: 20.0,
        })
        self.config.setdefault('smt_fee_per_point', 0.008)  # SMT费 元/焊点
        self.config.setdefault('dip_fee_per_point', 0.02)   # DIP费 元/焊点
        self.config.setdefault('test_fee', {
            'ICT': 0.5,
            'FCT': 1.0,
            'ATE': 2.0,
        })
        self.config.setdefault('overhead_rate', 0.10)
    
    def calculate(
        self,
        pcb_area_dm2: float,
        pcb_layers: int = 4,
        bom_cost: float = 0,
        smt_points: int = 500,
        dip_points: int = 50,
        test_type: str = 'FCT',
        **kwargs
    ) -> CostBreakdown:
        """计算PCBA成本"""
        # PCB成本
        pcb_price = self.config['pcb_price_per_dm2'].get(pcb_layers, 6.0)
        pcb_cost = pcb_area_dm2 * pcb_price
        
        # 元器件成本
        material_cost = bom_cost + pcb_cost
        
        # SMT/DIP加工费
        smt_cost = smt_points * self.config['smt_fee_per_point']
        dip_cost = dip_points * self.config['dip_fee_per_point']
        test_cost = self.config['test_fee'].get(test_type, 1.0)
        
        processing_cost = smt_cost + dip_cost + test_cost
        
        subtotal = material_cost + processing_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=0,
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={
                'pcb_cost': round(pcb_cost, 2),
                'smt_cost': round(smt_cost, 2),
            }
        )


class PowerSemiconductorCalculator(ComponentCostCalculator):
    """
    功率半导体(IGBT/MOS)成本计算器
    采用查表+参数估算
    """
    
    def load_default_params(self):
        # 按电流等级的参考价格
        self.config.setdefault('igbt_module_price', {
            (0, 100): 150.0,      # 100A以下
            (100, 200): 280.0,
            (200, 400): 450.0,
            (400, 600): 700.0,
            (600, 1000): 1200.0,
            (1000, 2000): 2500.0,
        })
        self.config.setdefault('voltage_factor', {
            650: 1.0,
            1200: 1.5,
            1700: 2.2,
        })
        self.config.setdefault('brand_factor', {
            '国产': 0.6,
            '英飞凌': 1.0,
            '三菱': 0.95,
            '富士': 0.9,
            '安森美': 0.85,
        })
    
    def calculate(
        self,
        current_rating_a: float,
        voltage_rating_v: int = 1200,
        brand: str = '英飞凌',
        quantity: int = 1,
        **kwargs
    ) -> CostBreakdown:
        """计算IGBT模块成本"""
        # 查找基础价格
        base_price = 500.0
        for (low, high), price in self.config['igbt_module_price'].items():
            if low <= current_rating_a < high:
                base_price = price
                break
        
        voltage_factor = self.config['voltage_factor'].get(voltage_rating_v, 1.0)
        brand_factor = self.config['brand_factor'].get(brand, 1.0)
        
        unit_price = base_price * voltage_factor * brand_factor
        total_cost = unit_price * quantity
        
        return CostBreakdown(
            material_cost=round(total_cost, 2),
            processing_cost=0,
            tooling_cost=0,
            overhead_cost=0,
            total_cost=round(total_cost, 2),
            details={
                'unit_price': round(unit_price, 2),
                'quantity': quantity,
                'spec': f'{current_rating_a}A/{voltage_rating_v}V',
            }
        )


# ============================================================
# 其他零部件计算器
# ============================================================

class PlasticInjectionCalculator(ComponentCostCalculator):
    """塑料注塑件成本计算器"""
    
    def load_default_params(self):
        self.config.setdefault('material_prices', {
            'ABS': 15.0,        # 元/kg
            'PA66': 25.0,
            'PA66+GF30': 28.0,
            'PBT': 22.0,
            'PPS': 80.0,
            'PEEK': 500.0,
        })
        self.config.setdefault('injection_fee', 5.0)       # 注塑费 元/kg
        self.config.setdefault('tooling_life', 300000)
        self.config.setdefault('overhead_rate', 0.08)
    
    def calculate(
        self,
        weight_kg: float,
        material: str = 'PA66+GF30',
        tooling_cost_total: float = 0,
        quantity: int = 1000,
        **kwargs
    ) -> CostBreakdown:
        """计算塑料注塑件成本"""
        material_price = self.config['material_prices'].get(material, 25.0)
        # 含损耗
        material_cost = weight_kg * 1.05 * material_price
        
        processing_cost = weight_kg * self.config['injection_fee']
        
        tooling_cost = 0
        if tooling_cost_total > 0:
            tooling_cost = tooling_cost_total / min(quantity, self.config['tooling_life'])
        
        subtotal = material_cost + processing_cost + tooling_cost
        overhead_cost = subtotal * self.config['overhead_rate']
        
        return CostBreakdown(
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            tooling_cost=round(tooling_cost, 2),
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(subtotal + overhead_cost, 2),
            details={'material': material}
        )


class ResolverCalculator(ComponentCostCalculator):
    """旋转变压器成本计算器"""
    
    def load_default_params(self):
        self.config.setdefault('price_by_type', {
            '单速': 80.0,
            '双速': 120.0,
            '多摩川': 200.0,
            '进口': 350.0,
        })
    
    def calculate(
        self,
        resolver_type: str = '单速',
        quantity: int = 1,
        **kwargs
    ) -> CostBreakdown:
        """计算旋变成本"""
        unit_price = self.config['price_by_type'].get(resolver_type, 100.0)
        total_cost = unit_price * quantity
        
        return CostBreakdown(
            material_cost=round(total_cost, 2),
            processing_cost=0,
            tooling_cost=0,
            overhead_cost=0,
            total_cost=round(total_cost, 2),
            details={'type': resolver_type, 'quantity': quantity}
        )


class ConnectorCalculator(ComponentCostCalculator):
    """连接器成本计算器"""
    
    def load_default_params(self):
        self.config.setdefault('price_by_pins', {
            (0, 10): 5.0,
            (10, 30): 15.0,
            (30, 60): 35.0,
            (60, 100): 60.0,
        })
        self.config.setdefault('type_factor', {
            '普通': 1.0,
            '防水': 2.0,
            '高压': 3.0,
            '汽车级': 2.5,
        })
    
    def calculate(
        self,
        pin_count: int,
        connector_type: str = '汽车级',
        quantity: int = 1,
        **kwargs
    ) -> CostBreakdown:
        """计算连接器成本"""
        base_price = 20.0
        for (low, high), price in self.config['price_by_pins'].items():
            if low <= pin_count < high:
                base_price = price
                break
        
        type_factor = self.config['type_factor'].get(connector_type, 1.0)
        unit_price = base_price * type_factor
        total_cost = unit_price * quantity
        
        return CostBreakdown(
            material_cost=round(total_cost, 2),
            processing_cost=0,
            tooling_cost=0,
            overhead_cost=0,
            total_cost=round(total_cost, 2),
            details={'pins': pin_count, 'type': connector_type}
        )


# ============================================================
# 成本计算引擎 - 统一入口
# ============================================================

class ComponentCostEngine:
    """
    零部件成本计算引擎
    统一管理所有零部件计算器
    """
    
    # 计算器注册表
    CALCULATORS = {
        # 铝制品
        '铝压铸': AluminumCastingCalculator,
        '铝机加工': AluminumMachiningCalculator,
        '铝挤压': AluminumExtrusionCalculator,
        '铝拉伸': AluminumExtrusionCalculator,
        
        # 钢制品/冲压件
        '冲压件': StampingCalculator,
        '硅钢片': SiliconSteelCalculator,
        '铁芯': SiliconSteelCalculator,
        
        # 电磁材料
        '磁钢': MagnetCalculator,
        '永磁体': MagnetCalculator,
        '铜线': CopperWindingCalculator,
        '绕组': CopperWindingCalculator,
        
        # 机械部件
        '轴': ShaftCalculator,
        '轴承': BearingCalculator,
        
        # 电子元器件
        'PCBA': PCBACalculator,
        '电路板': PCBACalculator,
        'IGBT': PowerSemiconductorCalculator,
        'MOS': PowerSemiconductorCalculator,
        '功率模块': PowerSemiconductorCalculator,
        
        # 其他
        '塑料件': PlasticInjectionCalculator,
        '塑料壳体': PlasticInjectionCalculator,
        '旋变': ResolverCalculator,
        '旋转变压器': ResolverCalculator,
        '连接器': ConnectorCalculator,
    }
    
    def __init__(self, config_path: str = None):
        """
        初始化引擎
        
        Args:
            config_path: 配置文件路径(JSON)
        """
        self.calculators: Dict[str, ComponentCostCalculator] = {}
        self.custom_config = {}
        
        if config_path:
            self.load_config(config_path)
        
        self._init_calculators()
    
    def _init_calculators(self):
        """初始化所有计算器"""
        for name, calc_class in self.CALCULATORS.items():
            config = self.custom_config.get(name, {})
            self.calculators[name] = calc_class(config)
    
    def load_config(self, path: str):
        """加载配置文件"""
        with open(path, 'r', encoding='utf-8') as f:
            self.custom_config = json.load(f)
    
    def save_config(self, path: str):
        """保存配置到文件"""
        config = {}
        for name, calc in self.calculators.items():
            config[name] = calc.config
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def calculate(
        self, 
        component_type: str, 
        **params
    ) -> CostBreakdown:
        """
        计算零部件成本
        
        Args:
            component_type: 零部件类型
            **params: 计算参数
            
        Returns:
            成本分解结果
        """
        if component_type not in self.calculators:
            # 尝试模糊匹配
            for key in self.calculators:
                if key in component_type or component_type in key:
                    component_type = key
                    break
            else:
                raise ValueError(f"未知的零部件类型: {component_type}")
        
        calculator = self.calculators[component_type]
        return calculator.calculate(**params)
    
    def calculate_bom(
        self, 
        bom_items: List[Dict]
    ) -> Dict:
        """
        计算整个BOM的成本
        
        Args:
            bom_items: BOM列表，每项包含component_type和参数
            
        Returns:
            BOM成本汇总
        """
        results = []
        total_cost = 0
        
        for item in bom_items:
            component_type = item.pop('component_type', item.pop('type', ''))
            quantity = item.get('quantity', 1)
            
            try:
                cost = self.calculate(component_type, **item)
                results.append({
                    'component': component_type,
                    'quantity': quantity,
                    'unit_cost': cost.total_cost,
                    'total_cost': cost.total_cost * quantity,
                    'breakdown': cost
                })
                total_cost += cost.total_cost * quantity
            except Exception as e:
                results.append({
                    'component': component_type,
                    'error': str(e)
                })
        
        return {
            'items': results,
            'total_bom_cost': round(total_cost, 2)
        }
    
    def get_available_types(self) -> List[str]:
        """获取支持的零部件类型"""
        return list(self.CALCULATORS.keys())
    
    def update_calculator_params(
        self, 
        component_type: str, 
        params: Dict
    ):
        """更新计算器参数"""
        if component_type in self.calculators:
            self.calculators[component_type].update_params(params)


def main():
    """示例用法"""
    print("=" * 60)
    print("零部件成本计算引擎 - 示例")
    print("=" * 60)
    
    engine = ComponentCostEngine()
    
    # 示例1: 铝压铸壳体
    print("\n【铝压铸壳体】")
    result = engine.calculate(
        '铝压铸',
        weight_kg=5.0,
        material='ADC12',
        machining_hours=0.5,
        surface_treatment='喷粉',
        surface_area_m2=0.15,
        tooling_cost_total=80000,
        quantity=5000
    )
    print(f"  材料成本: ¥{result.material_cost}")
    print(f"  加工成本: ¥{result.processing_cost}")
    print(f"  模具分摊: ¥{result.tooling_cost}")
    print(f"  总成本: ¥{result.total_cost}")
    
    # 示例2: 硅钢片铁芯
    print("\n【硅钢片铁芯】")
    result = engine.calculate(
        '硅钢片',
        weight_kg=25.0,
        material='50W470'
    )
    print(f"  总成本: ¥{result.total_cost}")
    
    # 示例3: BOM计算
    print("\n【完整BOM计算】")
    bom = [
        {'component_type': '铝压铸', 'weight_kg': 5.0, 'material': 'ADC12'},
        {'component_type': '硅钢片', 'weight_kg': 25.0},
        {'component_type': '磁钢', 'weight_kg': 2.0, 'grade': 'N42'},
        {'component_type': '铜线', 'weight_kg': 8.0},
        {'component_type': '轴', 'weight_kg': 3.0, 'diameter_mm': 45, 'length_mm': 250},
        {'component_type': '轴承', 'bore_diameter_mm': 45, 'quantity': 2},
        {'component_type': '旋变', 'resolver_type': '单速'},
    ]
    
    bom_result = engine.calculate_bom(bom)
    print(f"  BOM总成本: ¥{bom_result['total_bom_cost']}")
    for item in bom_result['items']:
        if 'error' not in item:
            print(f"    - {item['component']}: ¥{item['total_cost']}")


if __name__ == "__main__":
    main()
