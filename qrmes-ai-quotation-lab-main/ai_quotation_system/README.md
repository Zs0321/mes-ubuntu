# AI智能报价系统

> 工程机械电动化领域 - 电机及控制器智能报价解决方案

## 项目简介

本系统是一套面向电机和电机控制器制造企业的AI智能报价系统，主要功能包括：

- 📊 **历史数据分析**: 分析历史报价数据，识别定价模式和异常
- 🤖 **AI辅助报价**: 基于机器学习和LLM的智能报价推荐
- 📈 **价格预测**: 基于产品参数和BOM的价格预测模型
- 💬 **智能问答**: AI驱动的报价咨询助手

## 产品覆盖范围

| 产品类型 | 参数范围 |
|----------|----------|
| 永磁同步电机 | 3KW - 500KW |
| 电机控制器 | 48VDC - 800VDC |
| PDU | - |
| DCDC | - |
| OBC | - |

## 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装步骤

```bash
# 1. 克隆项目
git clone <repository_url>
cd ai_quotation_system

# 2. 创建虚拟环境
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量(可选，用于AI功能)
cp .env.example .env
# 编辑.env文件，添加LLM API Key
```

### 启动应用

```bash
streamlit run app.py
```

访问 http://localhost:8501 打开Web界面。

## 项目结构

```
ai_quotation_system/
├── app.py                 # Streamlit Web应用入口
├── requirements.txt       # Python依赖
├── README.md             # 项目说明
├── docs/                 # 文档
│   ├── spec.md          # 系统规格说明
│   └── framework_recommendation.md  # 框架推荐
└── src/                  # 源代码
    ├── __init__.py
    ├── data_analyzer.py  # 数据分析模块
    ├── price_predictor.py # 价格预测模块
    └── ai_assistant.py   # AI助手模块
```

## 核心功能

### 1. 数据分析

```python
from src.data_analyzer import QuotationDataAnalyzer

analyzer = QuotationDataAnalyzer()
analyzer.load_data('quotations.xlsx')
analyzer.clean_data()

# 价格分布分析
price_stats = analyzer.analyze_price_distribution()

# 异常检测
anomalies = analyzer.detect_anomalies_iqr()
```

### 2. 价格预测

```python
from src.price_predictor import PricePredictor, QuotationCalculator

# 基于规则的报价
calculator = QuotationCalculator()
result = calculator.calculate_quotation(
    bom_cost=8500,
    product_type='电机',
    quantity=50,
    customer_level='A'
)

# 基于ML的预测
predictor = PricePredictor()
predictor.train(df)
prediction = predictor.predict({
    'power_kw': 100,
    'voltage_v': 400,
    'quantity': 50,
    'bom_cost': 8500
})
```

### 3. AI分析

```python
from src.ai_assistant import QuotationAIAssistant

assistant = QuotationAIAssistant(
    provider='openai',
    api_key='your-api-key'
)

result = assistant.analyze_quotation({
    'product_type': '电机',
    'power_kw': 100,
    'bom_cost': 8500
})
```

## 配置说明

### LLM配置

支持多种LLM提供商：

| 提供商 | 环境变量 | 说明 |
|--------|----------|------|
| OpenAI | `OPENAI_API_KEY` | GPT-4, GPT-3.5 |
| 通义千问 | `DASHSCOPE_API_KEY` | Qwen系列 |
| 文心一言 | `WENXIN_API_KEY` | ERNIE系列 |

### 毛利率配置

可在侧边栏自定义各产品线的目标毛利率。

## 数据格式

### 导入数据字段

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| quotation_no | string | 否 | 报价单号 |
| product_type | string | 是 | 产品类型 |
| power_kw | float | 是 | 功率(KW) |
| voltage_v | int | 否 | 电压(V) |
| quantity | int | 是 | 数量 |
| unit_price | float | 是 | 单价 |
| bom_cost | float | 否 | BOM成本 |
| customer | string | 否 | 客户名称 |
| quotation_date | date | 否 | 报价日期 |

## 技术栈

- **后端**: Python, FastAPI(可选)
- **前端**: Streamlit, Plotly
- **ML**: Scikit-learn, XGBoost
- **AI**: LangChain, OpenAI/通义千问
- **数据处理**: Pandas, NumPy

## 开发计划

- [x] 基础数据分析功能
- [x] 规则引擎报价
- [x] ML价格预测
- [x] LLM集成
- [ ] 知识库RAG
- [ ] 批量报价导出
- [ ] 报价审批流程

## 许可证

MIT License

## 联系方式

如有问题或建议，请提交Issue。
