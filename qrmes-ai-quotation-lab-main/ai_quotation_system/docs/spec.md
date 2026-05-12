# AI智能报价系统 - 系统规格说明书

## 版本信息
- **版本**: v1.0.0
- **创建日期**: 2024-12-03
- **最后更新**: 2024-12-03
- **作者**: AI系统设计

---

## 1. 项目概述

### 1.1 背景
公司专注于工程机械电动化领域，主要产品包括：
- **永磁同步电机**: 功率范围 3KW - 500KW
- **电机控制器**: 电压范围 48VDC - 800VDC
- **配套产品**: PDU、DCDC、OBC等

### 1.2 核心需求
1. **历史数据分析**: 对几十份历史报价数据进行系统分析
2. **合理性评估**: 识别历史报价中的合理和不合理定价
3. **智能报价**: 基于产品参数、BOM快速生成价格预估
4. **AI辅助决策**: 引入AI进行深度分析和预测

### 1.3 主要原材料清单
| 类别 | 材料 |
|------|------|
| 铝制品 | 铝压铸、铝机加工、铝拉伸 |
| 机械部件 | 轴、轴承 |
| 电磁材料 | 硅钢片、磁钢、铜线 |
| 传感器 | 旋转变压器 |
| 电子元器件 | PCBA、IGBT、MOS、连接器、线束 |
| 结构件 | 塑料壳体 |

---

## 2. 系统架构

### 2.1 技术架构图
```
┌─────────────────────────────────────────────────────────────────┐
│                        前端界面层                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 数据上传    │  │ 报价查询    │  │ 分析报表Dashboard      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                        API服务层                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 数据导入API │  │ 报价计算API │  │ 分析报告API            │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                        AI引擎层                                  │
│  ┌───────────────────────┐  ┌───────────────────────────────┐   │
│  │ 数据分析引擎           │  │ 价格预测引擎                  │   │
│  │ - 异常检测            │  │ - 回归模型                    │   │
│  │ - 趋势分析            │  │ - 特征工程                    │   │
│  │ - 聚类分析            │  │ - 成本建模                    │   │
│  └───────────────────────┘  └───────────────────────────────┘   │
│  ┌───────────────────────┐  ┌───────────────────────────────┐   │
│  │ LLM分析引擎           │  │ 知识库引擎                    │   │
│  │ - 报价解读            │  │ - 历史案例                    │   │
│  │ - 建议生成            │  │ - 行业标准                    │   │
│  │ - 自然语言交互        │  │ - 材料价格                    │   │
│  └───────────────────────┘  └───────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                        数据层                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 历史报价库  │  │ 产品参数库  │  │ 材料价格库              │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ BOM数据库   │  │ 供应商库    │  │ 向量知识库              │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈选型

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **前端** | React + Ant Design Pro | 企业级管理后台 |
| **后端** | Python FastAPI | 高性能异步API |
| **数据库** | PostgreSQL + Redis | 结构化数据 + 缓存 |
| **向量库** | Milvus / Chroma | AI知识检索 |
| **AI框架** | LangChain + OpenAI/通义千问 | LLM编排 |
| **ML框架** | Scikit-learn + XGBoost | 传统机器学习 |
| **数据处理** | Pandas + NumPy | 数据分析 |
| **可视化** | ECharts / Plotly | 报表图表 |

---

## 3. 核心功能模块

### 3.1 数据导入与清洗模块

#### 3.1.1 功能描述
- 支持Excel/CSV格式历史报价导入
- 自动识别报价单结构
- 数据清洗和标准化
- 数据质量检查报告

#### 3.1.2 数据字段规范
```json
{
  "quotation_id": "报价单号",
  "product_type": "产品类型(电机/控制器/PDU/DCDC/OBC)",
  "product_model": "产品型号",
  "power_kw": "功率(KW)",
  "voltage_v": "电压(V)",
  "quantity": "数量",
  "unit_price": "单价",
  "total_price": "总价",
  "quotation_date": "报价日期",
  "customer": "客户",
  "status": "状态(成交/未成交)",
  "bom": {
    "materials": [
      {
        "name": "材料名称",
        "category": "材料类别",
        "quantity": "用量",
        "unit_cost": "单位成本"
      }
    ]
  }
}
```

### 3.2 历史数据分析模块

#### 3.2.1 合理性分析
- **价格区间分析**: 同类产品价格分布
- **成本占比分析**: BOM成本/报价比例
- **毛利率分析**: 不同产品线毛利率对比
- **异常检测**: 识别异常高/低报价

#### 3.2.2 趋势分析
- 材料价格趋势
- 产品价格趋势
- 季节性波动分析

#### 3.2.3 关联分析
- 功率-价格关系
- 电压-成本关系
- 批量-折扣关系

### 3.3 智能报价引擎

#### 3.3.1 基于规则的报价
```python
# 报价公式框架
报价 = BOM成本 × (1 + 毛利率) + 研发分摊 + 售后预留

其中:
- BOM成本 = Σ(材料成本 + 加工成本 + 人工成本)
- 毛利率 = f(产品类型, 批量, 客户等级)
- 研发分摊 = 研发投入 / 预计销量
- 售后预留 = 报价 × 售后费率
```

#### 3.3.2 AI预测报价
- **输入特征**: 功率、电压、BOM清单、数量、客户类型
- **输出**: 推荐报价区间、置信度

#### 3.3.3 LLM辅助分析
- 自然语言描述报价依据
- 与历史案例对比分析
- 风险提示和建议

### 3.4 知识库模块

#### 3.4.1 知识类型
- 产品技术规格
- 历史报价案例
- 材料价格信息
- 行业定价标准

#### 3.4.2 RAG检索
- 相似案例检索
- 技术参数匹配
- 智能问答

---

## 4. AI模型设计

### 4.1 价格预测模型

#### 4.1.1 特征工程
```python
特征列表 = {
    # 产品特征
    "power_kw": "功率",
    "voltage_v": "电压",
    "efficiency": "效率等级",
    "ip_rating": "防护等级",
    "cooling_type": "冷却方式",
    
    # BOM特征
    "aluminum_weight": "铝材重量",
    "copper_weight": "铜材重量",
    "magnet_weight": "磁钢重量",
    "pcba_count": "PCBA数量",
    "igbt_count": "IGBT数量",
    
    # 商务特征
    "quantity": "订单数量",
    "customer_level": "客户等级",
    "delivery_days": "交期要求"
}
```

#### 4.1.2 模型选择
| 模型 | 适用场景 | 优势 |
|------|----------|------|
| XGBoost | 价格预测 | 处理非线性关系,可解释性好 |
| 随机森林 | 特征重要性分析 | 稳定性好 |
| 线性回归 | 基准模型 | 简单直观 |
| 神经网络 | 复杂模式 | 拟合能力强 |

### 4.2 异常检测模型

#### 4.2.1 方法
- **统计方法**: Z-score、IQR
- **机器学习**: Isolation Forest、LOF
- **规则引擎**: 业务规则校验

### 4.3 LLM应用

#### 4.3.1 应用场景
1. **报价解读**: 生成报价说明文档
2. **案例分析**: 对比分析历史案例
3. **智能问答**: 回答定价相关问题
4. **异常解释**: 解释异常报价原因

#### 4.3.2 Prompt设计
```python
QUOTATION_ANALYSIS_PROMPT = """
你是一位专业的电机和电机控制器报价分析专家。

产品信息:
- 产品类型: {product_type}
- 功率: {power_kw} KW
- 电压: {voltage_v} V
- BOM成本: {bom_cost}

历史参考:
{similar_cases}

请分析:
1. 推荐报价区间
2. 定价依据
3. 风险提示
4. 优化建议
"""
```

---

## 5. 数据库设计

### 5.1 ER图
```
┌──────────────────┐       ┌──────────────────┐
│    Products      │       │   Quotations     │
├──────────────────┤       ├──────────────────┤
│ id              │───┐   │ id               │
│ model           │   │   │ quotation_no     │
│ type            │   └──>│ product_id       │
│ power_kw        │       │ customer_id      │
│ voltage_v       │       │ quantity         │
│ specifications  │       │ unit_price       │
└──────────────────┘       │ total_price      │
                           │ status           │
┌──────────────────┐       │ created_at       │
│    Customers     │       └──────────────────┘
├──────────────────┤              │
│ id              │──────────────┘
│ name            │
│ level           │       ┌──────────────────┐
│ industry        │       │   BOM_Items      │
└──────────────────┘       ├──────────────────┤
                           │ id               │
┌──────────────────┐       │ quotation_id     │
│   Materials      │───────│ material_id      │
├──────────────────┤       │ quantity         │
│ id              │       │ unit_cost        │
│ name            │       │ total_cost       │
│ category        │       └──────────────────┘
│ unit            │
│ current_price   │
│ price_history   │
└──────────────────┘
```

### 5.2 核心表结构

```sql
-- 产品表
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    model VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL, -- 电机/控制器/PDU/DCDC/OBC
    power_kw DECIMAL(10,2),
    voltage_v INTEGER,
    specifications JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 报价表
CREATE TABLE quotations (
    id SERIAL PRIMARY KEY,
    quotation_no VARCHAR(50) UNIQUE NOT NULL,
    product_id INTEGER REFERENCES products(id),
    customer_id INTEGER REFERENCES customers(id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    total_price DECIMAL(15,2) NOT NULL,
    bom_cost DECIMAL(12,2),
    margin_rate DECIMAL(5,2),
    status VARCHAR(20), -- 待审核/已成交/已失效
    created_at TIMESTAMP DEFAULT NOW()
);

-- 材料表
CREATE TABLE materials (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    unit VARCHAR(20),
    current_price DECIMAL(12,4),
    supplier_id INTEGER,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- BOM明细表
CREATE TABLE bom_items (
    id SERIAL PRIMARY KEY,
    quotation_id INTEGER REFERENCES quotations(id),
    material_id INTEGER REFERENCES materials(id),
    quantity DECIMAL(12,4),
    unit_cost DECIMAL(12,4),
    total_cost DECIMAL(15,2)
);
```

---

## 6. API接口设计

### 6.1 接口列表

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/quotations/import` | POST | 导入历史报价 |
| `/api/v1/quotations/analyze` | POST | 分析报价数据 |
| `/api/v1/quotations/predict` | POST | AI预测报价 |
| `/api/v1/quotations/{id}` | GET | 获取报价详情 |
| `/api/v1/products` | GET/POST | 产品管理 |
| `/api/v1/materials` | GET/POST | 材料管理 |
| `/api/v1/analysis/report` | GET | 分析报告 |
| `/api/v1/ai/chat` | POST | AI问答 |

### 6.2 报价预测接口

```json
// POST /api/v1/quotations/predict
// Request
{
  "product_type": "电机",
  "power_kw": 100,
  "voltage_v": 400,
  "quantity": 50,
  "customer_level": "A",
  "bom": [
    {"material": "铝压铸壳体", "quantity": 1, "unit": "件"},
    {"material": "硅钢片", "quantity": 50, "unit": "kg"},
    {"material": "磁钢", "quantity": 5, "unit": "kg"}
  ]
}

// Response
{
  "success": true,
  "data": {
    "recommended_price": 12500.00,
    "price_range": {
      "min": 11800.00,
      "max": 13200.00
    },
    "confidence": 0.85,
    "bom_cost": 8500.00,
    "margin_rate": 0.32,
    "similar_cases": [
      {
        "quotation_no": "Q2023-0156",
        "product": "100KW电机",
        "price": 12300.00,
        "similarity": 0.92
      }
    ],
    "analysis": "基于历史数据分析，该规格电机报价区间...",
    "recommendations": [
      "建议关注磁钢价格波动",
      "可考虑批量折扣策略"
    ]
  }
}
```

---

## 7. 实施计划

### 7.1 阶段划分

| 阶段 | 时间 | 内容 |
|------|------|------|
| **Phase 1** | 2周 | 数据导入、清洗、基础分析 |
| **Phase 2** | 2周 | 价格预测模型开发 |
| **Phase 3** | 2周 | LLM集成、知识库构建 |
| **Phase 4** | 2周 | 前端界面、系统集成 |
| **Phase 5** | 1周 | 测试优化、部署上线 |

### 7.2 交付物
1. 数据分析报告
2. AI报价系统
3. 用户操作手册
4. 系统部署文档

---

## 8. 更新日志

| 日期 | 版本 | 更新内容 | 更新原因 |
|------|------|----------|----------|
| 2024-12-03 | v1.0.0 | 初始版本创建 | 项目启动 |

---

## 附录

### A. 电机报价参考模型
```
电机报价 = 基础成本 + 功率增量成本 + 定制化成本 + 利润

其中:
- 基础成本 = 固定成本(壳体+轴承+传感器等)
- 功率增量成本 = 功率 × 单位功率成本系数
- 单位功率成本系数与(硅钢+磁钢+铜线)用量相关
- 定制化成本 = 非标要求的额外成本
```

### B. 控制器报价参考模型
```
控制器报价 = PCBA成本 + 功率器件成本 + 结构件成本 + 利润

其中:
- PCBA成本 = 固定成本 + 元器件BOM
- 功率器件成本 = IGBT/MOS数量 × 单价
- 功率器件选型与电压、电流相关
```
