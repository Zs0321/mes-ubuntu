# 零部件成本计算引擎 - 设计规格

## 版本信息

- **版本**: v1.0.0
- **创建日期**: 2024-12-03
- **最后更新**: 2024-12-03
- **更新内容**: 初始版本，支持15+种零部件成本计算

---

## 1. 设计目标

为不同类型的零部件建立基于经验公式的成本计算模型，支持：

- **参数化计算**: 根据重量、尺寸、材料等参数自动计算成本
- **可配置**: 所有计算参数可通过JSON配置文件调整
- **可扩展**: 易于添加新的零部件类型
- **经验积累**: 支持从历史数据学习优化参数

---

## 2. 零部件成本模型

### 2.1 铝压铸件

**成本公式:**

```
总成本 = 材料成本 + 压铸加工费 + 机加工费 + 表面处理费 + 模具分摊 + 管理费

其中:
- 材料成本 = 毛坯重量 × 材料单价
- 毛坯重量 = 净重 × (1 + 废品率 + 浇注系统系数)
- 压铸加工费 = 毛坯重量 × 压铸费率
- 机加工费 = 加工工时 × 机加费率
- 表面处理费 = 表面积 × 处理单价
- 模具分摊 = 模具总成本 / min(批量, 模具寿命)
- 管理费 = 小计 × 管理费率
```

**关键参数:**

| 参数 | 典型值 | 说明 |
|------|--------|------|
| ADC12单价 | 22元/kg | 常用压铸铝合金 |
| 压铸费率 | 8元/kg | 含设备折旧、人工 |
| 机加费率 | 80元/小时 | CNC加工 |
| 毛坯系数 | 1.15-1.20 | 浇注系统+损耗 |
| 模具寿命 | 10万件 | 压铸模具 |

### 2.2 冲压件

**成本公式:**

```
总成本 = 材料成本 + 冲压加工费 + 模具分摊 + 管理费

其中:
- 材料成本 = 毛坯重量 × 材料单价
- 毛坯重量 = 净重 / 材料利用率
- 冲压加工费 = 冲次费 × 工序系数 × 每件冲次
- 模具分摊 = 模具总成本 / min(批量, 模具寿命)
```

**关键参数:**

| 参数 | 典型值 | 说明 |
|------|--------|------|
| SPCC单价 | 6.5元/kg | 冷轧板 |
| SECC单价 | 8.5元/kg | 镀锌板 |
| 材料利用率 | 75% | 落料效率 |
| 模具寿命 | 50万件 | 冲压模具 |

**工序系数:**

| 工序数 | 系数 |
|--------|------|
| 1 | 1.0 |
| 2 | 1.8 |
| 3 | 2.5 |
| 4 | 3.2 |
| 5+ | 4.0 |

### 2.3 硅钢片(铁芯)

**成本公式:**

```
总成本 = 材料成本 + 冲片费 + 叠压费 + 绝缘处理费 + 管理费

其中:
- 材料成本 = 毛坯重量 × 材料单价
- 毛坯重量 = 净重 / 材料利用率
- 冲片费 = 净重 × 冲片费率
- 叠压费 = 净重 × 叠压费率
- 绝缘处理费 = 净重 × 绝缘费率
```

**硅钢片牌号与价格:**

| 牌号 | 价格(元/kg) | 铁损(W/kg) | 适用场景 |
|------|-------------|------------|----------|
| 50W800 | 6.5 | 8.0 | 低成本 |
| 50W600 | 7.5 | 6.0 | 标准 |
| 50W470 | 9.0 | 4.7 | 高效 |
| 35W300 | 12.0 | 3.0 | 高效紧凑 |
| 35W250 | 15.0 | 2.5 | 高端 |

### 2.4 磁钢(永磁体)

**成本公式:**

```
总成本 = 材料成本 + 加工费 + 镀层费 + 管理费

其中:
- 材料成本 = 重量 × 牌号单价
- 加工费 = 重量 × 加工费率
- 镀层费 = 重量 × 镀层费率 (通常镀镍)
```

**磁钢牌号与价格:**

| 牌号 | 价格(元/kg) | 磁能积(MGOe) | 工作温度 |
|------|-------------|--------------|----------|
| N35 | 180 | 35 | ≤80°C |
| N42 | 250 | 42 | ≤80°C |
| N48 | 400 | 48 | ≤80°C |
| N35SH | 280 | 35 | ≤150°C |
| N42SH | 350 | 42 | ≤150°C |
| N42UH | 450 | 42 | ≤180°C |

### 2.5 铜线绕组

**成本公式:**

```
总成本 = 材料成本 + 绕线加工费 + 管理费

其中:
- 材料成本 = 重量 × (铜价 + 漆包线加价 + 绝缘等级加价)
- 绕线加工费 = 重量 × 绕线费率
```

**绕线费率:**

| 绕组类型 | 费率(元/kg) | 说明 |
|----------|-------------|------|
| 简单 | 20 | 大槽、少匝 |
| 中等 | 35 | 标准绕组 |
| 复杂 | 55 | 多极、细线 |
| 扁线 | 80 | 扁铜线绕组 |

### 2.6 轴类零件

**成本公式:**

```
总成本 = 材料成本 + 车削加工费 + 热处理费 + 管理费

其中:
- 材料成本 = 毛坯重量 × 材料单价
- 毛坯重量 ≈ π × (D×1.12/2)² × (L+10) × 密度
- 车削加工费 = 工时 × 机加费率
- 热处理费 = 净重 × 热处理费率
```

### 2.7 功率半导体(IGBT/MOS)

**成本公式:**

```
单价 = 基础价格 × 电压系数 × 品牌系数

基础价格按电流等级查表
电压系数: 650V=1.0, 1200V=1.5, 1700V=2.2
```

**基础价格参考:**

| 电流等级(A) | 价格(元) |
|-------------|----------|
| 0-100 | 150 |
| 100-200 | 280 |
| 200-400 | 450 |
| 400-600 | 700 |
| 600-1000 | 1200 |

---

## 3. 架构设计

### 3.1 类图

```
ComponentCostCalculator (抽象基类)
    ├── AluminumCastingCalculator    # 铝压铸
    ├── AluminumMachiningCalculator  # 铝机加工
    ├── AluminumExtrusionCalculator  # 铝挤压
    ├── StampingCalculator           # 冲压件
    ├── SiliconSteelCalculator       # 硅钢片
    ├── MagnetCalculator             # 磁钢
    ├── CopperWindingCalculator      # 铜线绕组
    ├── ShaftCalculator              # 轴
    ├── BearingCalculator            # 轴承
    ├── PCBACalculator               # 电路板
    ├── PowerSemiconductorCalculator # IGBT/MOS
    ├── PlasticInjectionCalculator   # 塑料注塑
    ├── ResolverCalculator           # 旋变
    └── ConnectorCalculator          # 连接器

ComponentCostEngine (统一入口)
    ├── calculate(component_type, **params)
    ├── calculate_bom(bom_items)
    ├── load_config(path)
    └── save_config(path)
```

### 3.2 数据流

```
用户输入参数
     │
     ▼
ComponentCostEngine.calculate()
     │
     ▼
┌──────────────────────┐
│  选择对应的Calculator │
└──────────────────────┘
     │
     ▼
┌──────────────────────┐
│  加载经验参数配置     │
│  (JSON配置文件)       │
└──────────────────────┘
     │
     ▼
┌──────────────────────┐
│  执行成本公式计算     │
└──────────────────────┘
     │
     ▼
CostBreakdown (成本分解结果)
├── material_cost    # 材料成本
├── processing_cost  # 加工成本
├── tooling_cost     # 模具分摊
├── overhead_cost    # 管理费用
├── total_cost       # 总成本
└── details          # 详细信息
```

---

## 4. 配置文件说明

配置文件位置: `config/component_cost_params.json`

### 4.1 配置结构

```json
{
  "零部件类型": {
    "_公式说明": "成本公式描述",
    "material_prices": {
      "材料牌号": 单价
    },
    "加工费率": 费率值,
    "其他参数": 参数值
  }
}
```

### 4.2 如何更新参数

1. **直接编辑JSON**: 修改 `config/component_cost_params.json`
2. **代码更新**:

```python
engine = ComponentCostEngine()
engine.update_calculator_params('铝压铸', {
    'casting_fee': 9.0  # 更新压铸费率
})
engine.save_config('config/component_cost_params.json')
```

3. **从历史数据学习** (规划中):

```python
engine.learn_from_history(historical_data)
```

---

## 5. 使用示例

### 5.1 单个零部件计算

```python
from src.component_cost_engine import ComponentCostEngine

engine = ComponentCostEngine()

# 计算铝压铸壳体成本
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

print(f"材料成本: ¥{result.material_cost}")
print(f"加工成本: ¥{result.processing_cost}")
print(f"模具分摊: ¥{result.tooling_cost}")
print(f"总成本: ¥{result.total_cost}")
```

### 5.2 完整BOM计算

```python
# 100KW电机BOM示例
motor_bom = [
    {'component_type': '铝压铸', 'weight_kg': 15.0, 'material': 'ADC12',
     'machining_hours': 2.0, 'tooling_cost_total': 150000, 'quantity': 5000},
    {'component_type': '硅钢片', 'weight_kg': 35.0, 'material': '50W470'},
    {'component_type': '磁钢', 'weight_kg': 3.5, 'grade': 'N42SH'},
    {'component_type': '铜线', 'weight_kg': 12.0, 'winding_type': '中等'},
    {'component_type': '轴', 'weight_kg': 5.0, 'material': '42CrMo',
     'diameter_mm': 55, 'length_mm': 300, 'heat_treatment': '调质'},
    {'component_type': '轴承', 'bore_diameter_mm': 55, 'bearing_type': '深沟球',
     'brand': '国产优质', 'quantity': 2},
    {'component_type': '旋变', 'resolver_type': '单速'},
    {'component_type': '塑料件', 'weight_kg': 0.8, 'material': 'PA66+GF30'},
    {'component_type': '连接器', 'pin_count': 35, 'connector_type': '防水', 'quantity': 2},
]

bom_result = engine.calculate_bom(motor_bom)
print(f"BOM总成本: ¥{bom_result['total_bom_cost']}")
```

---

## 6. 扩展指南

### 6.1 添加新零部件类型

1. 创建Calculator类:

```python
class NewComponentCalculator(ComponentCostCalculator):
    def load_default_params(self):
        self.config.setdefault('param1', default_value)
    
    def calculate(self, **params) -> CostBreakdown:
        # 实现成本计算逻辑
        return CostBreakdown(...)
```

2. 注册到引擎:

```python
ComponentCostEngine.CALCULATORS['新零部件'] = NewComponentCalculator
```

### 6.2 参数学习优化(规划)

```python
# 从历史实际成本数据优化参数
def optimize_params(historical_costs: pd.DataFrame):
    """
    使用历史数据优化计算参数
    
    historical_costs包含:
    - component_type: 零部件类型
    - params: 输入参数
    - actual_cost: 实际成本
    """
    # 使用回归/优化算法拟合参数
    pass
```

---

## 7. 更新日志

| 日期 | 版本 | 更新内容 | 更新原因 |
|------|------|----------|----------|
| 2024-12-03 | v1.0.0 | 初始版本，支持15种零部件 | 项目需求 |

---

## 附录: 完整零部件类型列表

| 类型 | 别名 | Calculator |
|------|------|------------|
| 铝压铸 | - | AluminumCastingCalculator |
| 铝机加工 | - | AluminumMachiningCalculator |
| 铝挤压 | 铝拉伸 | AluminumExtrusionCalculator |
| 冲压件 | - | StampingCalculator |
| 硅钢片 | 铁芯 | SiliconSteelCalculator |
| 磁钢 | 永磁体 | MagnetCalculator |
| 铜线 | 绕组 | CopperWindingCalculator |
| 轴 | - | ShaftCalculator |
| 轴承 | - | BearingCalculator |
| PCBA | 电路板 | PCBACalculator |
| IGBT | MOS, 功率模块 | PowerSemiconductorCalculator |
| 塑料件 | 塑料壳体 | PlasticInjectionCalculator |
| 旋变 | 旋转变压器 | ResolverCalculator |
| 连接器 | - | ConnectorCalculator |
