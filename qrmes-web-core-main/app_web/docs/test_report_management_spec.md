# 测试报告管理模块 Spec

## 1. 概述

### 1.1 模块目标
建立一个测试报告管理系统，能够：
1. 自动扫描并解析 NAS 上的反电势测试 Word 文档
2. 提取结构化测试数据（序列号、测试结果、测试值等）
3. 与现有 MES 系统（物料扫码、工序照片）关联
4. 生成产品出厂完整信息报告
5. 提供测试数据统计分析功能

### 1.2 数据源路径
```
/volume2/测试中心/3、下线台架测试 Offline test data/1、台架测试数据/3、反电势数据/
├── 柳工双12油泵/                    # 项目文件夹
│   ├── 反电势_2025_09_28_15_34_40/  # 测试批次文件夹
│   ├── TZ80013925090008 2025 09 28 16 34 27 Pass.docx  # 测试报告
│   └── ...
├── 三一5T油泵/
└── ...
```

---

## 2. Word 文档数据结构

### 2.1 测试报告内容（从截图分析）

| 字段 | 说明 | 示例 |
|------|------|------|
| 测试模块 | 产品型号/测试类型 | 柳工双 12 油泵 |
| 说明 | 测试备注 | - |
| 测试结果 | 通过/失败 | 通过 |
| 校验测试值 | 包含名称、值、最小值、最大值 | 柳工双12油泵: 11.128, 6, 16 |
| 记录测试值 | 序列号 | TZ180014025110005 |
| 总线记录 | 附件文件 | 柳工双12油泵.blf |
| 运行记录 | 步骤文件 | Steps.ini |

### 2.2 文件名解析规则
```
TZ80013925090008 2025 09 28 16 34 27 Pass.docx
│                │                    │
├── 序列号        ├── 测试时间          └── 测试结果
```

---

## 3. 功能模块设计

### 3.1 数据采集模块
- **目录扫描器**：递归扫描项目文件夹，识别 .docx 文件
- **Word 解析器**：使用 `python-docx` 解析文档表格结构
- **数据提取器**：提取序列号、测试结果、校验值等结构化数据
- **增量同步**：只处理新增/修改的文件

### 3.2 数据存储模块
- **数据库表**：`test_reports`, `test_values`, `test_attachments`
- **关联字段**：通过序列号与 MES 物料记录关联

### 3.3 报告生成模块
- **出厂报告模板**：整合物料信息 + 工序照片 + 测试数据
- **输出格式**：PDF / Word / HTML
- **批量生成**：支持按项目/日期批量导出

### 3.4 统计分析模块
- **合格率统计**：按项目/日期/型号
- **测试值趋势**：均值、标准差、CPK
- **异常检测**：超出规格限值的产品
- **可视化图表**：折线图、柱状图、直方图

---

## 4. 技术选型

### 4.1 核心框架
| 功能 | 推荐库 | 说明 |
|------|--------|------|
| Word 解析 | `python-docx` | 读取 .docx 表格和内容 |
| 数据处理 | `pandas` | 数据清洗、统计分析 |
| 数据库 | `SQLite` / `SQLAlchemy` | 结构化存储 |
| 报告生成 | `docxtpl` / `WeasyPrint` | 模板化 Word/PDF 生成 |
| 图表可视化 | `matplotlib` / `plotly` | 统计图表 |
| Web 界面 | Flask (现有) | 管理界面 |

### 4.2 可参考的成熟框架
1. **Apache Superset** - 数据可视化和 BI 分析
2. **Metabase** - 轻量级数据分析平台
3. **Pandas Profiling** - 自动化数据分析报告
4. **Streamlit** - 快速搭建数据分析 Web 应用

---

## 5. 数据库设计

### 5.1 测试报告表 `test_reports`
```sql
CREATE TABLE test_reports (
    id INTEGER PRIMARY KEY,
    serial_number TEXT NOT NULL,          -- 产品序列号
    project_name TEXT,                    -- 项目名称（文件夹名）
    test_module TEXT,                     -- 测试模块
    test_result TEXT,                     -- 测试结果（Pass/Fail）
    test_time DATETIME,                   -- 测试时间
    file_path TEXT,                       -- 原始文件路径
    file_name TEXT,                       -- 文件名
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(serial_number, test_time)
);
```

### 5.2 测试值表 `test_values`
```sql
CREATE TABLE test_values (
    id INTEGER PRIMARY KEY,
    report_id INTEGER REFERENCES test_reports(id),
    value_name TEXT,                      -- 测试项名称
    value REAL,                           -- 实测值
    min_value REAL,                       -- 最小规格
    max_value REAL,                       -- 最大规格
    is_pass BOOLEAN,                      -- 是否合格
    value_type TEXT                       -- 类型：校验值/记录值
);
```

### 5.3 附件表 `test_attachments`
```sql
CREATE TABLE test_attachments (
    id INTEGER PRIMARY KEY,
    report_id INTEGER REFERENCES test_reports(id),
    attachment_type TEXT,                 -- 类型：总线记录/运行记录
    file_name TEXT,
    file_path TEXT
);
```

---

## 6. API 设计

### 6.1 数据采集
- `POST /api/test-reports/scan` - 扫描并导入测试报告
- `GET /api/test-reports/sync-status` - 获取同步状态

### 6.2 报告查询
- `GET /api/test-reports` - 列表查询（支持分页/筛选）
- `GET /api/test-reports/<serial>` - 按序列号查询
- `GET /api/test-reports/<id>/detail` - 报告详情

### 6.3 报告生成
- `POST /api/test-reports/generate-factory-report` - 生成出厂报告
- `GET /api/test-reports/download/<report_id>` - 下载报告

### 6.4 统计分析
- `GET /api/test-reports/statistics` - 综合统计
- `GET /api/test-reports/trend` - 趋势分析
- `GET /api/test-reports/cpk` - CPK 分析

---

## 7. 前端界面

### 7.1 测试报告管理页面
- 项目树形导航
- 报告列表（支持搜索、筛选、排序）
- 报告详情查看
- 批量操作（导出、删除）

### 7.2 出厂报告生成页面
- 选择序列号
- 预览整合信息（物料 + 照片 + 测试数据）
- 生成并下载 PDF

### 7.3 统计分析仪表板
- 合格率趋势图
- 测试值分布图
- 异常产品列表
- 导出分析报告

---

## 8. 实施计划

### Phase 1: 数据采集（1-2天）
- [ ] 实现目录扫描器
- [ ] 实现 Word 解析器
- [ ] 创建数据库表
- [ ] 实现增量同步

### Phase 2: 数据管理（1-2天）
- [ ] 实现 API 接口
- [ ] 创建管理界面
- [ ] 实现搜索和筛选

### Phase 3: 报告生成（2-3天）
- [ ] 设计出厂报告模板
- [ ] 整合物料、照片、测试数据
- [ ] 实现 PDF 生成

### Phase 4: 统计分析（2-3天）
- [ ] 实现统计计算
- [ ] 创建可视化图表
- [ ] 构建分析仪表板

---

## 9. 与现有系统集成

### 9.1 关联字段
- **序列号**：`test_reports.serial_number` ↔ MES 物料记录
- **项目名称**：`test_reports.project_name` ↔ 项目配置

### 9.2 数据流
```
反电势测试数据 ──┐
                 │
物料扫码记录 ────┼──→ 产品完整信息 ──→ 出厂报告
                 │
工序照片 ────────┘
```

---

## 10. 更新记录

| 日期 | 版本 | 更新内容 | 更新人 |
|------|------|----------|--------|
| 2025-12-03 | v1.0 | 初始设计 | Cascade |
