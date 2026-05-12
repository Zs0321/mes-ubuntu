# QC API 接口契约（手机端 → Web 后端）

> 手机端已按此契约完成开发，Web 后端需实现以下 3 个 API
> Base URL: `http://172.16.30.2:8891`
> 认证方式: Basic Auth（与现有 API 一致）

---

## 1. POST `/api/qc/analyze` — 提交照片进行 QC 分析

手机端拍照上传后，调用此接口将照片发送到后端，后端调用千问 Vision API 进行质检分析。

### 请求体

```json
{
  "product_serial": "TZ180014025110005",
  "process_name": "插磁钢",
  "process_index": 1,
  "project_name": "三一重卡230油冷电机",
  "product_type": "油泵电机总成",
  "photo_base64": [
    "/9j/4AAQSkZJRg..."
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_serial | string | 是 | 产品序列号 |
| process_name | string | 是 | 工序名称 |
| process_index | int | 是 | 工序序号（从1开始） |
| project_name | string | 是 | 项目名称 |
| product_type | string | 是 | 产品类型 |
| photo_base64 | string[] | 是 | 照片 base64 编码数组（无前缀，纯 base64） |

### 响应体

```json
{
  "success": true,
  "status": "pass",
  "confidence": 0.85,
  "summary": "工序照片检查合格，磁钢安装位置正确，数量完整",
  "findings": [
    {
      "type": "missing_material",
      "severity": "minor",
      "description": "第3号槽位磁钢边缘有轻微偏移",
      "location": "转子第3号槽位",
      "confidence": 0.65
    }
  ],
  "checklist": {
    "磁钢数量完整": true,
    "磁钢方向正确": true,
    "无明显损伤": true
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 请求是否成功 |
| status | string | 三级判定: `"pass"` / `"fail"` / `"ng"` |
| confidence | float | 置信度 0.0-1.0 |
| summary | string | 中文分析总结 |
| findings | array | 发现的问题列表 |
| findings[].type | string | 缺陷类型: `missing_material` / `misalignment` / `contamination` / `damage` / `incomplete` / `measurement_error` |
| findings[].severity | string | 严重程度: `critical` / `major` / `minor` |
| findings[].description | string | 缺陷描述（中文） |
| findings[].location | string | 缺陷位置描述 |
| findings[].confidence | float | 该发现的置信度 |
| checklist | object | 检查项结果 key→bool |
| error | string? | 失败时的错误信息 |

### 判定标准（参照 motor-qc）

| 判定 | 条件 |
|------|------|
| pass | 所有 checklist 项为 true，无 critical/major 缺陷，confidence > 0.8 |
| fail | 存在任何 critical 缺陷，或 2 个以上 major 缺陷 |
| ng | 存在 1 个 major 缺陷，或 confidence < 0.6，需人工复核 |

### 千问 API 未配置时

如果千问 API Key 尚未配置，返回：

```json
{
  "success": true,
  "status": "ng",
  "confidence": 0.0,
  "summary": "QC 视觉分析服务未配置，需人工复核",
  "findings": [],
  "checklist": {}
}
```

---

## 2. GET `/api/qc/check-previous/{serial}` — 检查前面工序状态

手机端在拍第 N 个工序照片前，调用此接口检查前 N-1 个工序是否已上传照片、QC 是否通过。

### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| serial | path | string | 是 | 产品序列号 |
| processIndex | query | int | 是 | 当前工序序号（检查此序号之前的所有工序） |
| projectName | query | string | 是 | 项目名称 |
| productType | query | string | 是 | 产品类型 |

### 示例请求

```
GET /api/qc/check-previous/TZ180014025110005?processIndex=4&projectName=三一重卡230油冷电机&productType=油泵电机总成
```

### 响应体

```json
{
  "success": true,
  "current_process_index": 4,
  "previous_steps": [
    {
      "process_name": "插磁钢",
      "order": 1,
      "has_photo": true,
      "qc_status": "pass"
    },
    {
      "process_name": "磁钢点胶",
      "order": 2,
      "has_photo": false,
      "qc_status": null
    },
    {
      "process_name": "铁芯叠压",
      "order": 3,
      "has_photo": true,
      "qc_status": "ng"
    }
  ],
  "all_passed": false,
  "missing_photos": ["磁钢点胶"],
  "failed_steps": [],
  "ng_steps": ["铁芯叠压"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 请求是否成功 |
| current_process_index | int | 当前工序序号 |
| previous_steps | array | 前面每个工序的状态 |
| previous_steps[].process_name | string | 工序名称 |
| previous_steps[].order | int | 工序序号 |
| previous_steps[].has_photo | bool | 是否已上传照片 |
| previous_steps[].qc_status | string? | QC 状态: `"pass"` / `"fail"` / `"ng"` / `null`(未检) |
| all_passed | bool | 前面工序是否全部通过（has_photo=true 且 qc_status="pass"） |
| missing_photos | string[] | 缺少照片的工序名称列表 |
| failed_steps | string[] | QC 未通过的工序名称列表 |
| ng_steps | string[] | 需人工复核的工序名称列表 |
| error | string? | 失败时的错误信息 |

### 特殊说明

- `processIndex` 传入当前要拍照的工序序号，接口返回该序号之前所有工序的状态
- 如果传入 `processIndex=1`（第一个工序），返回空的 `previous_steps`，`all_passed=true`
- 手机端也会传入一个很大的 `processIndex`（如 maxOrder+1）来获取所有工序状态用于列表显示

---

## 3. GET `/api/qc/config/{projectName}` — 获取项目 QC 策略配置

手机端加载项目时获取 QC 策略，决定是否启用 QC 检查、严苛度等。

### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| projectName | path | string | 是 | 项目名称 |

### 响应体

```json
{
  "success": true,
  "data": {
    "qc_enabled": true,
    "enforcement_mode": "warn",
    "check_previous_photos": true,
    "realtime_qc_enabled": true,
    "vision_model": "qwen-vl-max",
    "confidence_threshold": 0.8
  }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| qc_enabled | bool | false | 是否启用 QC 功能 |
| enforcement_mode | string | "warn" | `"warn"` = 警告但允许继续, `"block"` = 强制阻断 |
| check_previous_photos | bool | true | 是否检查前面工序照片 |
| realtime_qc_enabled | bool | true | 是否启用拍照后实时 QC 识别 |
| vision_model | string | "qwen-vl-max" | 千问模型选择 |
| confidence_threshold | float | 0.8 | 置信度阈值 |

### 项目未配置 QC 时

返回默认值（QC 关闭）：

```json
{
  "success": true,
  "data": {
    "qc_enabled": false,
    "enforcement_mode": "warn",
    "check_previous_photos": true,
    "realtime_qc_enabled": true,
    "vision_model": "qwen-vl-max",
    "confidence_threshold": 0.8
  }
}
```

---

## 4. GET `/api/qc/report/{serial}` — 获取电机完整检验报告

手机端通过扫描或输入序列号，查看整台电机的完整检验报告，包括每个工序的照片完整性和 QC 识别结果。

### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| serial | path | string | 是 | 产品序列号 |

### 示例请求

```
GET /api/qc/report/TZ180014025110005
```

### 响应体

```json
{
  "success": true,
  "serial_number": "TZ180014025110005",
  "overall_status": "ng",
  "project_name": "三一重卡230油冷电机",
  "product_type": "油泵电机总成",
  "total_processes": 13,
  "inspected_processes": 11,
  "missing_processes": ["整机气密检测", "电机电性能测试"],
  "results": [
    {
      "process": "插磁钢",
      "order": 1,
      "status": "pass",
      "confidence": 0.92,
      "summary": "磁钢安装位置正确，数量完整",
      "has_photo": true,
      "photo_count": 3,
      "defect_count": 0,
      "defects": []
    },
    {
      "process": "磁钢点胶",
      "order": 2,
      "status": "fail",
      "confidence": 0.88,
      "summary": "点胶覆盖不完整",
      "has_photo": true,
      "photo_count": 2,
      "defect_count": 1,
      "defects": [
        {
          "type": "incomplete",
          "severity": "major",
          "description": "3号槽位点胶未完全覆盖磁钢边缘",
          "location": "转子3号槽位",
          "confidence": 0.85
        }
      ]
    },
    {
      "process": "整机气密检测",
      "order": 12,
      "status": null,
      "confidence": 0,
      "summary": "",
      "has_photo": false,
      "photo_count": 0,
      "defect_count": 0,
      "defects": []
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 请求是否成功 |
| serial_number | string | 产品序列号 |
| overall_status | string | 整机总判定: `"pass"` / `"fail"` / `"ng"` |
| project_name | string | 项目名称 |
| product_type | string | 产品类型 |
| total_processes | int | 总工序数 |
| inspected_processes | int | 已检测工序数 |
| missing_processes | string[] | 缺失的工序名称列表 |
| results | array | 每个工序的检验结果（按 order 排序） |
| results[].process | string | 工序名称 |
| results[].order | int | 工序序号 |
| results[].status | string? | QC 状态: `"pass"` / `"fail"` / `"ng"` / `null`(未检) |
| results[].confidence | float | 置信度 0.0-1.0 |
| results[].summary | string | 分析摘要（中文） |
| results[].has_photo | bool | 是否已上传照片 |
| results[].photo_count | int | 照片数量 |
| results[].defect_count | int | 缺陷数量 |
| results[].defects | array | 缺陷详情列表 |
| results[].defects[].type | string | 缺陷类型 |
| results[].defects[].severity | string | 严重程度: `critical` / `major` / `minor` |
| results[].defects[].description | string | 缺陷描述（中文） |
| results[].defects[].location | string | 缺陷位置 |
| results[].defects[].confidence | float | 该发现的置信度 |

### 未找到该序列号时

```json
{
  "success": false,
  "error": "未找到序列号 TZ180014025110005 的检验记录"
}
```

---

## 建议的后端实现路径

1. 在项目配置 JSON 中新增 `qcPolicy` 字段存储 QC 策略
2. 新建 `qc_vision_api.py` Flask Blueprint，注册到 `mesapp.py`
3. 新建 `qwen_vision_client.py` 封装千问 VL API 调用（OpenAI 兼容格式）
4. 新建 SQLite 表 `qc_inspections` 存储 QC 分析结果
5. `/api/qc/check-previous` 查询照片表 + qc_inspections 表组合返回
6. `/api/qc/report/{serial}` 聚合照片表 + qc_inspections 表 + 项目配置，返回完整报告
