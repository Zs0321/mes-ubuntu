# 零部件成本计算 - 开源项目、论文与架构参考

## 版本信息

- **创建日期**: 2024-12-03
- **目的**: 收集整理零部件成本估算相关的开源项目、学术论文和行业框架

---

## 1. 学术论文

### 1.1 基于深度学习的制造成本预测

**论文**: Explainable Artificial Intelligence for Manufacturing Cost Estimation and Machining Feature Visualization

- **作者**: Soyoung Yoo, Namwoo Kang
- **发表**: Expert Systems with Applications, 2021
- **链接**: https://arxiv.org/abs/2010.14824
- **核心内容**:
  - 使用3D深度学习模型预测CNC加工成本
  - 采用3D Grad-CAM可视化影响成本的加工特征
  - 能识别和区分相同特征的不同加工难度
  - 为设计阶段提供降本指导

**论文**: Machine Learning-Based Manufacturing Cost Prediction from 2D Drawings

- **链接**: https://arxiv.org/html/2508.12440v1
- **核心内容**:
  - 从2D工程图纸提取200+几何和统计描述符
  - 基于13,680个零件数据训练模型
  - 替代传统需要人工工艺规划的报价流程

**论文**: A framework for analytical cost estimation of mechanical components

- **发表**: Springer - International Journal of Advanced Manufacturing Technology, 2020
- **链接**: https://link.springer.com/article/10.1007/s00170-020-05068-5
- **核心内容**:
  - 制造和成本相关知识的形式化框架
  - 将资深工艺师的经验知识转化为可计算的模型
  - 支持设计阶段快速分析估算成本

**论文**: A Cost Estimation Model for Machining Operations - ANN Parametric Approach

- **链接**: ResearchGate
- **核心内容**:
  - 使用人工神经网络进行机加工成本估算
  - 考虑电力消耗、冷却液、润滑油、刀具和切屑等活动
  - 提供最小加工成本的切削参数优化方法

### 1.2 基于活动的成本核算 (Activity-Based Costing, ABC)

**核心思想**: 将间接成本分配到具体的作业活动，而非简单按产量分摊

**主要步骤**:
1. 识别活动（如设置机器、加工、检验）
2. 为每个活动分配成本
3. 确定成本动因（如机器小时、零件数量）
4. 计算活动成本率
5. 将成本分配到产品

---

## 2. 开源项目

### 2.1 BOM管理类

| 项目 | 链接 | 说明 |
|------|------|------|
| **IndaBOM** | https://indabom.com | 免费开源BOM管理工具，集成Google Drive和Octopart成本估算 |
| **OpenBOM** | https://www.openbom.com | 云端BOM/PLM管理，支持CAD数据成本估算 |
| **KiCost** | https://github.com/hildogjr/KiCost | KiCad电子BOM成本计算，生成Excel报价单 |

### 2.2 云成本估算类（参考架构）

| 项目 | Stars | 链接 | 可借鉴点 |
|------|-------|------|----------|
| **Infracost** | 11.9k | https://github.com/infracost/infracost | 从配置文件解析资源，查表计算成本 |
| **ec2instances.info** | 5.6k | https://github.com/vantage-sh/ec2instances.info | 规格参数化查询定价 |
| **Crane** | 2k | https://github.com/gocrane/crane | 预测+优化框架 |

### 2.3 制造成本相关

| 项目 | 链接 | 说明 |
|------|------|------|
| **GEstimator** | https://github.com/manuvarkey/GEstimator | 土木工程估价软件，带详细工料分析 |
| **Materials-Cost-Calculator** | https://github.com/TechProofreader/Materials-Cost-Calculator | Python材料成本计算脚本 |

---

## 3. 商业软件架构参考

### 3.1 DFMA (Design for Manufacture and Assembly)

- **厂商**: Boothroyd Dewhurst
- **网站**: https://www.dfma.com
- **功能**:
  - Should-Cost Analysis（应成本分析）
  - 工艺特征识别
  - 全球制造流程成本数据库
  - 设计阶段成本优化

### 3.2 aPriori

- **网站**: https://www.apriori.com
- **功能**:
  - 3D CAD模型自动识别特征
  - 数字工厂模拟
  - 实时成本计算
  - 供应商谈判支持

### 3.3 CNCCookbook CADCAM Estimator

- **网站**: https://www.cnccookbook.com
- **功能**:
  - 基于切削参数的加工时间估算
  - 机床小时费率计算
  - 材料成本核算

---

## 4. 成本估算方法论

### 4.1 Should-Cost Model（应成本模型）

**公式框架**:

```
总成本 = 材料成本 + 加工成本 + 间接成本 + 利润

其中:
- 材料成本 = 毛坯重量 × 材料单价
- 加工成本 = Σ(各工序时间 × 工序费率)
- 间接成本 = 直接成本 × 管理费率
```

**关键成本类别**:
1. **Overhead/Indirect Costs** - 间接成本（设备折旧、租金、水电）
2. **Material Costs** - 材料成本
3. **Labor Costs** - 人工成本
4. **Machine Costs** - 设备成本
5. **Setup Costs** - 设置成本
6. **Tooling Costs** - 工装刀具成本
7. **Quality Costs** - 质量检验成本
8. **Outside Services** - 外协服务成本

### 4.2 Feature-Based Costing（基于特征的成本核算）

**核心思想**: 识别零件的加工特征，每个特征对应一个成本贡献

**特征类型**:
- 孔（通孔、盲孔、螺纹孔）
- 型腔（方形、圆形、复杂轮廓）
- 平面（粗加工、精加工）
- 曲面（2.5D、3D）
- 倒角/圆角

**成本计算**:
```
零件成本 = 基础成本 + Σ(特征i的成本)
特征成本 = f(特征类型, 尺寸参数, 精度要求, 加工难度)
```

### 4.3 Parametric Cost Estimation（参数化成本估算）

**回归模型**:
```
Cost = a₀ + a₁×Weight + a₂×Complexity + a₃×Tolerance + ...
```

**机器学习模型**:
- Random Forest
- XGBoost
- Neural Networks
- Support Vector Regression

---

## 5. 数据结构建议

### 5.1 零部件成本知识库Schema

```json
{
  "component_type": "铝压铸",
  "cost_model": {
    "type": "formula",
    "formula": "material + casting + machining + surface + tooling + overhead",
    "variables": {
      "material": {
        "formula": "weight * material_price * gross_factor",
        "params": {
          "gross_factor": {"default": 1.18, "range": [1.1, 1.3]}
        }
      },
      "casting": {
        "formula": "weight * casting_rate",
        "params": {
          "casting_rate": {"default": 8.0, "unit": "元/kg"}
        }
      }
    }
  },
  "lookup_tables": {
    "material_prices": {
      "ADC12": 22.0,
      "A380": 24.0
    }
  },
  "learning_data": {
    "historical_records": 150,
    "model_accuracy": 0.92,
    "last_trained": "2024-12-01"
  }
}
```

### 5.2 工艺知识库

```yaml
process: CNC_Milling
parameters:
  - name: material_removal_rate
    unit: cm³/min
    depends_on: [material, tool_type, machine_power]
  - name: surface_finish
    unit: Ra
    affects: [processing_time, tool_wear]
    
cost_drivers:
  - cutting_time: volume / material_removal_rate
  - tool_cost: cutting_time * tool_wear_rate * tool_price
  - machine_cost: (setup_time + cutting_time) * hourly_rate
```

---

## 6. 推荐实现路线

### Phase 1: 基础框架（当前已完成）
- ✅ 零部件成本计算引擎
- ✅ 经验参数JSON配置
- ✅ 15种零部件计算器

### Phase 2: 知识库增强
- [ ] 工艺路线知识库
- [ ] 加工特征识别
- [ ] 成本动因分析

### Phase 3: 机器学习优化
- [ ] 从历史数据学习参数
- [ ] 异常成本检测
- [ ] 成本预测模型

### Phase 4: 高级功能
- [ ] CAD特征自动提取（需集成CAD API）
- [ ] 供应商报价对比
- [ ] 成本优化建议

---

## 7. 参考资源链接汇总

### 学术资源
- arXiv Manufacturing Cost Papers: https://arxiv.org/search/?query=manufacturing+cost+estimation
- ResearchGate Costing Research: https://www.researchgate.net/topic/Cost-Estimation

### GitHub资源
- Cost Estimation Topic: https://github.com/topics/cost-estimation
- Cost Model Topic: https://github.com/topics/cost-model

### 行业标准
- ASME B89.7.3.1 - 测量不确定度指南
- ISO 15686-5 - 建筑全生命周期成本

### 在线工具
- CNC Cookbook: https://www.cnccookbook.com
- CustomPartNet: https://www.custompartnet.com（免费成本估算）

---

## 更新日志

| 日期 | 更新内容 |
|------|----------|
| 2024-12-03 | 初始版本，收集整理开源项目和论文资源 |
