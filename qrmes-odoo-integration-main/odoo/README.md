# Odoo 集成模块

本目录包含 QR MES 系统与 Odoo ERP 的集成配置和自定义模块。

---

## 📋 目录结构

```
odoo/
├── README.md                       # 本文件
├── docker-compose.yml              # Odoo + PostgreSQL 容器编排
├── .env.example                    # 环境变量模板
├── config/
│   └── odoo.conf                   # Odoo 配置文件
├── addons/                         # 自定义 Odoo 模块
│   └── qrmes_integration/          # QR MES 集成模块
│       ├── __init__.py
│       ├── __manifest__.py
│       ├── models/
│       ├── views/
│       └── security/
├── scripts/                        # 安装和管理脚本
│   ├── install.sh                  # 一键安装脚本
│   ├── backup.sh                   # 备份脚本
│   └── restore.sh                  # 恢复脚本
└── data/                           # 数据文件
    ├── demo_data.xml
    └── initial_config.xml
```

---

## 🚀 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
vim .env  # 根据实际情况修改配置
```

### 2. 启动 Odoo 和 PostgreSQL

```bash
# 使用 Docker Compose 启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 3. 访问 Odoo

- **Web 界面**: http://localhost:8069
- **初始用户名**: admin
- **初始密码**: admin（首次登录后会要求修改）

### 4. 安装 QR MES 集成模块

1. 登录 Odoo
2. 进入 "应用" (Apps)
3. 搜索 "QR MES Integration"
4. 点击 "安装"

---

## ⚙️ 配置说明

### Docker Compose 配置

主要服务：

- **PostgreSQL 15**: Odoo 数据库
- **Odoo 17**: ERP 系统

端口映射：

- `8069`: Odoo Web 界面
- `5432`: PostgreSQL 数据库

### Odoo 配置文件

`config/odoo.conf` 包含 Odoo 的运行时配置：

- 数据库连接参数
- 日志级别
- 工作进程数
- 附件存储路径
- 自定义模块路径

---

## 🔌 集成说明

### QR MES 与 Odoo 集成架构

```
┌─────────────────────────────────────────────────────────────┐
│                      集成架构                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐                      ┌──────────────┐    │
│  │  Flask Web   │   REST API / RPC     │    Odoo      │    │
│  │  (QR MES)    │ ◄─────────────────► │    ERP       │    │
│  │              │                      │              │    │
│  │ • 照片管理    │                      │ • 制造(MRP)  │    │
│  │ • 质量检测    │                      │ • 质量(QMS)  │    │
│  │ • 测试报告    │                      │ • 库存(WMS)  │    │
│  │ • 设备采集    │                      │ • 工单管理   │    │
│  └──────────────┘                      └──────────────┘    │
│         │                                      │            │
│         │                                      │            │
│         ▼                                      ▼            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │             PostgreSQL 数据库                        │   │
│  │  ├── qrmes (QR MES 数据)                            │   │
│  │  └── odoo (Odoo ERP 数据)                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 集成内容

1. **工单同步**: Odoo MRP 工单 → QR MES 测试任务
2. **质量报告**: QR MES 测试结果 → Odoo QMS 质量检验单
3. **物料信息**: Odoo 产品信息 ↔ QR MES 项目配置
4. **工时统计**: QR MES 测试工时 → Odoo 工时记录
5. **照片附件**: QR MES 照片 → Odoo 附件系统

---

## 📦 自定义模块开发

### 创建新模块

```bash
cd addons
odoo scaffold my_module
```

### 模块结构

```
qrmes_integration/
├── __init__.py                     # 模块初始化
├── __manifest__.py                 # 模块清单
├── models/                         # 数据模型
│   ├── __init__.py
│   ├── qrmes_project.py
│   └── qrmes_test_report.py
├── views/                          # 视图定义
│   ├── qrmes_project_views.xml
│   └── qrmes_test_report_views.xml
├── security/                       # 权限控制
│   └── ir.model.access.csv
├── data/                           # 初始数据
│   └── qrmes_data.xml
└── static/                         # 静态资源
    └── description/
        └── icon.png
```

---

## 🔧 常用命令

### Docker 管理

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f odoo

# 进入 Odoo 容器
docker exec -it qrmes-odoo bash

# 进入 PostgreSQL 容器
docker exec -it qrmes-postgres psql -U odoo
```

### Odoo 管理

```bash
# 更新模块
docker exec -it qrmes-odoo odoo -u qrmes_integration -d odoo

# 安装模块
docker exec -it qrmes-odoo odoo -i qrmes_integration -d odoo

# 初始化数据库
docker exec -it qrmes-odoo odoo --init=base -d odoo --stop-after-init

# 备份数据库
docker exec qrmes-postgres pg_dump -U odoo odoo > backup_$(date +%Y%m%d).sql

# 恢复数据库
docker exec -i qrmes-postgres psql -U odoo odoo < backup_20251204.sql
```

---

## 🐛 故障排查

### 问题 1: Odoo 无法启动

```bash
# 查看详细日志
docker-compose logs odoo

# 检查数据库连接
docker exec qrmes-postgres psql -U odoo -c "SELECT version();"

# 重置 Odoo 数据库（谨慎操作）
docker-compose down -v
docker-compose up -d
```

### 问题 2: 模块安装失败

```bash
# 检查模块路径
docker exec qrmes-odoo ls -la /mnt/extra-addons/

# 检查模块依赖
docker exec qrmes-odoo odoo --help

# 重新加载模块列表
# 在 Odoo Web 界面：应用 → 更新应用列表
```

### 问题 3: 数据库连接问题

```bash
# 检查 PostgreSQL 状态
docker-compose ps postgres

# 测试连接
docker exec qrmes-odoo psql -h postgres -U odoo -d odoo

# 检查网络
docker network inspect qrmes-odoo-network
```

---

## 📚 参考资料

- [Odoo 官方文档](https://www.odoo.com/documentation/17.0/)
- [Odoo 开发指南](https://www.odoo.com/documentation/17.0/developer.html)
- [PostgreSQL 文档](https://www.postgresql.org/docs/15/)

---

**创建日期**: 2025-12-04  
**维护者**: Cascade AI  
**版本**: v1.0
