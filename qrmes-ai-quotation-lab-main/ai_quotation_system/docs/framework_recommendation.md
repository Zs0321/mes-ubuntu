# AI报价系统 - 框架与方案推荐

## 版本信息

- **版本**: v1.0.0
- **创建日期**: 2024-12-03
- **最后更新**: 2024-12-03

---

## 1. 推荐技术方案

### 1.1 方案一：轻量级方案（推荐起步）

适合快速验证，数据量较小（几十到几百条）的场景。

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit Web界面                   │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│              Python分析引擎                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Pandas   │  │ Sklearn  │  │ LangChain+LLM   │  │
│  │ 数据处理  │  │ ML模型   │  │ 智能分析         │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│              SQLite + Excel文件                      │
└─────────────────────────────────────────────────────┘
```

**技术栈:**

| 组件 | 技术 | 说明 |
|------|------|------|
| 界面 | Streamlit | 快速构建数据应用 |
| 数据处理 | Pandas | 数据分析利器 |
| 机器学习 | Scikit-learn | 价格预测 |
| AI分析 | LangChain + 通义千问/GPT | 智能解读 |
| 数据存储 | SQLite | 轻量数据库 |
| 可视化 | Plotly | 交互式图表 |

**优势:**

- 开发周期短（1-2周可出原型）
- 部署简单，单机即可运行
- 迭代快速，易于调整

### 1.2 方案二：企业级方案

适合数据量大、需要多用户协作的场景。

```
┌─────────────────────────────────────────────────────┐
│           React + Ant Design Pro 前端                │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│               FastAPI 后端服务                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ 数据服务  │  │ 分析服务  │  │ AI服务           │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│  PostgreSQL  │  Redis  │  Milvus向量库             │
└─────────────────────────────────────────────────────┘
```

---

## 2. 核心框架详解

### 2.1 数据分析框架

#### Pandas + NumPy

```python
# 数据加载与清洗示例
import pandas as pd
import numpy as np

class QuotationAnalyzer:
    def __init__(self, data_path):
        self.df = pd.read_excel(data_path)
        self.clean_data()
    
    def clean_data(self):
        """数据清洗"""
        # 处理缺失值
        self.df = self.df.dropna(subset=['unit_price', 'power_kw'])
        # 异常值处理
        self.df = self.df[self.df['unit_price'] > 0]
    
    def analyze_price_distribution(self, product_type):
        """价格分布分析"""
        subset = self.df[self.df['product_type'] == product_type]
        return {
            'mean': subset['unit_price'].mean(),
            'std': subset['unit_price'].std(),
            'median': subset['unit_price'].median(),
            'min': subset['unit_price'].min(),
            'max': subset['unit_price'].max(),
            'q25': subset['unit_price'].quantile(0.25),
            'q75': subset['unit_price'].quantile(0.75)
        }
    
    def detect_anomalies(self, method='iqr'):
        """异常检测"""
        if method == 'iqr':
            Q1 = self.df['unit_price'].quantile(0.25)
            Q3 = self.df['unit_price'].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            anomalies = self.df[
                (self.df['unit_price'] < lower_bound) | 
                (self.df['unit_price'] > upper_bound)
            ]
        return anomalies
```

### 2.2 机器学习框架

#### XGBoost + Scikit-learn

```python
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score
import xgboost as xgb

class PricePredictionModel:
    def __init__(self):
        self.model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.label_encoders = {}
    
    def prepare_features(self, df):
        """特征工程"""
        features = df[[
            'power_kw', 'voltage_v', 'quantity',
            'bom_cost', 'customer_level', 'product_type'
        ]].copy()
        
        # 编码分类变量
        for col in ['customer_level', 'product_type']:
            if col not in self.label_encoders:
                self.label_encoders[col] = LabelEncoder()
                features[col] = self.label_encoders[col].fit_transform(features[col])
            else:
                features[col] = self.label_encoders[col].transform(features[col])
        
        return features
    
    def train(self, df):
        """训练模型"""
        X = self.prepare_features(df)
        y = df['unit_price']
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        self.model.fit(X_train_scaled, y_train)
        
        # 评估
        y_pred = self.model.predict(X_test_scaled)
        metrics = {
            'mae': mean_absolute_error(y_test, y_pred),
            'r2': r2_score(y_test, y_pred)
        }
        return metrics
    
    def predict(self, features):
        """预测价格"""
        X = self.prepare_features(features)
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)
    
    def get_feature_importance(self):
        """特征重要性"""
        importance = self.model.feature_importances_
        return dict(zip(self.model.feature_names_in_, importance))
```

### 2.3 LLM集成框架

#### LangChain + 通义千问/OpenAI

```python
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory

class AIQuotationAssistant:
    def __init__(self, api_key, model="gpt-4"):
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0.3
        )
        self.memory = ConversationBufferMemory()
        
    def analyze_quotation(self, quotation_data, similar_cases):
        """分析报价并给出建议"""
        prompt = ChatPromptTemplate.from_template("""
你是一位专业的电机和电机控制器报价分析专家。

## 当前报价信息
- 产品类型: {product_type}
- 功率: {power_kw} KW
- 电压: {voltage_v} V
- 数量: {quantity}
- BOM成本: {bom_cost} 元
- 目标客户: {customer}

## 相似历史案例
{similar_cases}

## 请提供以下分析

### 1. 推荐报价区间
基于历史数据和成本分析，给出合理的报价区间。

### 2. 定价依据
说明定价的主要考虑因素。

### 3. 风险提示
指出可能的定价风险点。

### 4. 优化建议
提供可能的成本优化或报价策略建议。
        """)
        
        chain = LLMChain(llm=self.llm, prompt=prompt)
        
        response = chain.run(
            product_type=quotation_data['product_type'],
            power_kw=quotation_data['power_kw'],
            voltage_v=quotation_data['voltage_v'],
            quantity=quotation_data['quantity'],
            bom_cost=quotation_data['bom_cost'],
            customer=quotation_data.get('customer', '未知'),
            similar_cases=self._format_cases(similar_cases)
        )
        
        return response
    
    def _format_cases(self, cases):
        """格式化历史案例"""
        if not cases:
            return "暂无相似案例"
        
        formatted = []
        for i, case in enumerate(cases, 1):
            formatted.append(f"""
案例{i}:
- 产品: {case['product']}
- 功率: {case['power_kw']}KW
- 报价: {case['unit_price']}元
- 成交状态: {case['status']}
- 相似度: {case['similarity']:.2%}
            """)
        return "\n".join(formatted)
    
    def explain_anomaly(self, quotation, reason):
        """解释异常报价"""
        prompt = ChatPromptTemplate.from_template("""
以下报价被标记为异常，请分析可能的原因：

报价信息:
{quotation}

异常原因:
{reason}

请从以下角度分析:
1. 可能的业务合理性解释
2. 如果确实是错误，可能的原因
3. 建议的处理方式
        """)
        
        chain = LLMChain(llm=self.llm, prompt=prompt)
        return chain.run(quotation=str(quotation), reason=reason)
```

### 2.4 知识库与RAG

#### 使用Chroma向量数据库

```python
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

class QuotationKnowledgeBase:
    def __init__(self, persist_directory="./chroma_db"):
        self.embeddings = OpenAIEmbeddings()
        self.persist_directory = persist_directory
        self.vectorstore = None
        
    def build_from_documents(self, docs_path):
        """从文档构建知识库"""
        # 加载文档
        loader = DirectoryLoader(docs_path, glob="**/*.txt")
        documents = loader.load()
        
        # 文档分割
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        splits = text_splitter.split_documents(documents)
        
        # 创建向量存储
        self.vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=self.embeddings,
            persist_directory=self.persist_directory
        )
        self.vectorstore.persist()
        
    def add_quotation_case(self, quotation):
        """添加报价案例到知识库"""
        text = f"""
报价案例:
- 报价单号: {quotation['quotation_no']}
- 产品: {quotation['product']}
- 功率: {quotation['power_kw']}KW
- 电压: {quotation['voltage_v']}V
- 报价: {quotation['unit_price']}元
- 成本: {quotation['bom_cost']}元
- 毛利率: {quotation['margin_rate']:.2%}
- 成交状态: {quotation['status']}
- 日期: {quotation['date']}
        """
        self.vectorstore.add_texts([text])
        
    def search_similar_cases(self, query, k=5):
        """搜索相似案例"""
        if not self.vectorstore:
            self.vectorstore = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings
            )
        
        results = self.vectorstore.similarity_search_with_score(query, k=k)
        return results
```

---

## 3. 数据分析流程

### 3.1 历史数据分析流程

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  数据导入   │───>│  数据清洗   │───>│  特征提取   │
└─────────────┘    └─────────────┘    └─────────────┘
                                            │
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  报告生成   │<───│ AI解读分析  │<───│  统计分析   │
└─────────────┘    └─────────────┘    └─────────────┘
```

### 3.2 分析维度

| 维度 | 分析内容 | 方法 |
|------|----------|------|
| **价格合理性** | 价格是否在合理区间 | 统计分布、Z-score |
| **成本占比** | BOM成本占报价比例 | 比例分析 |
| **毛利分析** | 不同产品毛利率 | 分组统计 |
| **趋势分析** | 价格时间趋势 | 时序分析 |
| **关联分析** | 功率-价格关系 | 回归分析 |
| **异常检测** | 异常报价识别 | IQR、Isolation Forest |

---

## 4. 快速启动指南

### 4.1 环境准备

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 4.2 requirements.txt

```
# 数据处理
pandas>=2.0.0
numpy>=1.24.0
openpyxl>=3.1.0

# 机器学习
scikit-learn>=1.3.0
xgboost>=2.0.0

# AI/LLM
langchain>=0.1.0
openai>=1.0.0
chromadb>=0.4.0

# Web界面
streamlit>=1.28.0
plotly>=5.18.0

# 数据库
sqlalchemy>=2.0.0

# 其他
python-dotenv>=1.0.0
pydantic>=2.0.0
```

### 4.3 启动应用

```bash
# 启动Streamlit应用
streamlit run app.py
```

---

## 5. 推荐开发路线

### 第一阶段：数据准备与分析（1周）

1. 收集整理历史报价Excel
2. 设计统一的数据格式
3. 开发数据导入清洗脚本
4. 完成基础统计分析

### 第二阶段：AI分析集成（1周）

1. 集成LLM进行报价解读
2. 开发异常检测模块
3. 构建报价知识库

### 第三阶段：预测模型（1周）

1. 特征工程
2. 模型训练与调优
3. 模型评估与验证

### 第四阶段：系统集成（1周）

1. 开发Web界面
2. 系统集成测试
3. 部署上线

---

## 更新日志

| 日期 | 版本 | 更新内容 | 更新原因 |
|------|------|----------|----------|
| 2024-12-03 | v1.0.0 | 初始版本 | 项目启动 |
