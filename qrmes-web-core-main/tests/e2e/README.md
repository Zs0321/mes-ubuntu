# E2E 自动化测试系统

## 概述

这是一个完整的端到端（E2E）自动化测试和修复系统，使用 Playwright 进行浏览器自动化测试，并通过 Agent Team 协作模式实现智能循环修复。

## 系统架构

- **Coordinator**: 协调整个测试-修复循环
- **Test Runner**: 执行 Playwright E2E 测试
- **Analyzer**: 分析测试失败原因
- **Fixer**: 自动修复代码问题
- **Deployer**: 部署到测试服务器并进行健康检查

## 前置条件

1. **测试账号**: 需要在 `tests/e2e/config.py` 中配置真实的测试账号
2. **sshpass**: 确保已安装 sshpass（用于 SSH 自动认证）
3. **测试服务器**: 确保测试服务器 (172.16.30.2:8891) 可访问

## 安装依赖

```bash
pip install -r tests/e2e/requirements.txt
playwright install chromium
```

## 配置测试账号

编辑 `tests/e2e/config.py`，更新测试账号信息：

```python
'test_user': {
    'username': 'your_test_username',  # 替换为真实测试账号
    'password': 'your_test_password'   # 替换为真实密码
}
```

## 运行测试

### 运行完整的自动化测试和修复循环

```bash
python run_automated_testing.py
```

### 指定 Playwright 浏览器（可选）

默认优先使用 `chromium`（在部分 macOS 环境可规避 Firefox Nightly 启动崩溃）：

```bash
PW_BROWSER=chromium pytest tests/e2e/ -v
```

### 运行单个测试模块

```bash
# 认证测试
pytest tests/e2e/auth/test_authentication.py -v

# 记录查询测试
pytest tests/e2e/records/test_records.py -v

# 运行所有测试
pytest tests/e2e/ -v
```

## 测试覆盖

当前已实现的测试模块：

1. **认证测试** (5 个测试)
   - 正常登录
   - 错误密码
   - 登出功能
   - 未授权访问
   - 会话保持

2. **记录查询测试** (6 个测试)
   - 页面加载
   - 按项目查询
   - 按序列号查询
   - 按日期范围查询
   - 控制台错误检测
   - API 端点测试

## 待实现的测试模块

- 照片管理测试
- 统计页面测试
- API 端点测试
- 报告上传测试
- 报告管理测试
- Motor QC 测试
- 工序配置测试
- 权限管理测试

## 工作流程

1. **第一轮测试**: 运行所有测试，收集失败信息
2. **分析失败**: 分类问题类型（JS 错误、API 错误、数据库错误等）
3. **自动修复**: 根据分析结果自动修复代码
4. **部署验证**: 部署到测试服务器并进行健康检查
5. **重新测试**: 验证修复效果
6. **循环执行**: 重复上述步骤，最多 5 轮

## 停止条件

- ✅ 所有测试通过
- ⏱️ 达到最大迭代次数（5 轮）
- 🔄 检测到循环（连续 2 轮相同失败）
- ❌ 关键服务无法启动

## 预期效果

- **第一轮**: 发现 15-20 个问题
- **第二轮**: 剩余 5-8 个问题
- **第三轮**: 剩余 0-3 个问题
- **成功标准**: 至少 90% 测试通过，无 P0/P1 问题

## 目录结构

```
tests/e2e/
├── __init__.py
├── config.py                 # 测试配置
├── conftest.py              # pytest fixtures
├── README.md                # 本文档
├── requirements.txt         # Python 依赖
├── pytest.ini              # pytest 配置
├── agents/                 # Agent Team 组件
│   ├── __init__.py
│   └── coordinator.py      # 协调器
├── auth/                   # 认证测试
│   ├── __init__.py
│   └── test_authentication.py
├── records/                # 记录查询测试
│   ├── __init__.py
│   └── test_records.py
└── utils/                  # 工具类
    ├── __init__.py
    ├── console_monitor.py  # 控制台监控
    └── health_checker.py   # 健康检查
```

## 故障排除

### 测试失败

1. 检查测试账号是否正确配置
2. 检查测试服务器是否可访问
3. 查看截图：`test_results/screenshots/`
4. 查看测试报告：`test_results/reports/report.html`

### 部署失败

1. 检查 sshpass 是否已安装
2. 检查 SSH 连接是否正常
3. 查看服务器日志：`/volume2/MES/test/logs/app.log`

## 贡献

欢迎贡献更多测试用例和改进建议！
