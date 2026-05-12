# MES系统开发者文档

## 目录

1. [开发环境搭建](#开发环境搭建)
2. [项目结构](#项目结构)
3. [核心模块说明](#核心模块说明)
4. [开发规范](#开发规范)
5. [测试指南](#测试指南)
6. [部署流程](#部署流程)
7. [扩展开发](#扩展开发)

---

## 开发环境搭建

### 1.1 系统要求

- **操作系统：** Linux (推荐Ubuntu 20.04+) 或 macOS
- **Python版本：** 3.8+
- **数据库：** SQLite 3.x, H2 Database
- **其他：** Git, Node.js (用于前端开发)

### 1.2 安装依赖

#### 克隆项目
```bash
git clone <repository-url>
cd mes-system
```

#### 创建虚拟环境
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows
```

#### 安装Python依赖
```bash
pip install -r requirements.txt
```

#### requirements.txt内容
```
Flask==2.3.0
Flask-CORS==4.0.0
requests==2.31.0
pandas==2.0.0
openpyxl==3.1.0
python-dateutil==2.8.2
Werkzeug==2.3.0
```

### 1.3 配置开发环境

#### 创建配置文件
```bash
cp config.example.py config.py
```

#### 编辑配置文件
```python
# config.py
class DevelopmentConfig:
    DEBUG = True
    TESTING = False
    
    # 使用本地文件系统
    USE_WEBDAV = False
    NAS_LOCAL_BASE_PATH = './dev_data'
    
    # 数据库配置
    SQLITE_DATABASE_PATH = './dev_data/users.db'
    H2_DATABASE_PATH = './dev_data/product_records.db'
    
    # 群晖API配置（开发环境可以mock）
    SYNOLOGY_HOST = 'localhost'
    SYNOLOGY_PORT = '5000'
    SYNOLOGY_USE_HTTPS = False
```

#### 初始化开发数据
```bash
python initialize_system.py
```

### 1.4 启动开发服务器

```bash
# 启动Flask应用
python mesapp.py

# 或使用Flask开发服务器
export FLASK_APP=mesapp.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=8891
```

访问：`http://localhost:8891`

---

## 项目结构

```
mes-system/
├── app_web/                    # Web后台应用
│   ├── mesapp.py              # 主应用文件
│   ├── config.py              # 配置文件
│   ├── auth.py                # 认证模块
│   ├── data_access_layer.py  # 数据访问层
│   ├── permission_service.py  # 权限服务
│   ├── user_management_service.py  # 用户管理
│   ├── synology_auth_client.py     # 群晖认证客户端
│   ├── photo_api.py           # 照片管理API
│   ├── process_config_api.py  # 工序配置API
│   ├── project_config_manager.py   # 项目配置管理
│   ├── config_history_manager.py   # 配置历史管理
│   ├── h2_api.py              # H2数据库API
│   ├── error_handler.py       # 错误处理
│   ├── security_validator.py  # 安全验证
│   ├── webdav_client_v2.py    # WebDAV客户端
│   ├── smb_client.py          # SMB客户端
│   ├── static/                # 静态文件
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   ├── templates/             # HTML模板
│   │   ├── admin/
│   │   └── base.html
│   ├── docs/                  # 文档
│   ├── deployment/            # 部署脚本
│   └── tests/                 # 测试文件
│
├── app/                       # Android移动应用
│   └── src/
│       └── main/
│           ├── java/
│           │   └── com/testcenter/qrscanner/
│           │       ├── auth/              # 认证模块
│           │       ├── photo/             # 照片管理
│           │       ├── process/           # 工序记录
│           │       ├── config/            # 配置管理
│           │       ├── network/           # 网络通信
│           │       ├── database/          # 数据库
│           │       └── ui/                # UI组件
│           └── res/                       # 资源文件
│
└── .kiro/                     # 项目规范
    └── specs/
        └── user-permission-and-process-recording/
            ├── requirements.md
            ├── design.md
            └── tasks.md
```

---

## 核心模块说明

### 3.1 认证模块 (auth.py)

#### 主要功能
- 群晖账户认证
- 会话管理
- 权限验证装饰器

#### 核心类和函数

```python
class UserManager:
    """用户管理器"""
    
    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """认证用户"""
        pass
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """根据用户名获取用户"""
        pass
    
    def create_or_update_user(self, username: str, display_name: str) -> Dict:
        """创建或更新用户"""
        pass

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """管理员权限验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or user.get('role') != 'admin':
            return jsonify({'success': False, 'error': '权限不足'}), 403
        return f(*args, **kwargs)
    return decorated_function
```

### 3.2 权限服务 (permission_service.py)

#### 主要功能
- 权限检查
- 权限日志记录
- 权限缓存

#### 核心类

```python
class PermissionService:
    """权限服务"""
    
    def __init__(self):
        self.cache = {}
        self.cache_timeout = 600  # 10分钟
    
    def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """检查用户权限"""
        pass
    
    def log_permission_check(self, user_id: str, resource: str, 
                            action: str, result: str):
        """记录权限检查"""
        pass
    
    def get_user_permissions(self, user_id: str) -> List[str]:
        """获取用户权限列表"""
        pass
```

### 3.3 照片管理 (photo_api.py)

#### 主要功能
- 照片上传
- 照片查询
- 照片元数据管理

#### 核心函数

```python
@app.route('/api/photos/upload', methods=['POST'])
@login_required
def upload_photo():
    """上传工序照片"""
    pass

@app.route('/api/photos', methods=['GET'])
@login_required
def get_photos():
    """获取照片列表"""
    pass

@app.route('/api/photos/<int:photo_id>', methods=['GET'])
@login_required
def get_photo_detail(photo_id):
    """获取照片详情"""
    pass

@app.route('/api/photos/<int:photo_id>/download', methods=['GET'])
@login_required
def download_photo(photo_id):
    """下载照片"""
    pass
```

### 3.4 工序配置 (process_config_api.py)

#### 主要功能
- 工序配置管理
- 配置历史记录
- 配置同步

#### 核心类

```python
class ProcessConfigManager:
    """工序配置管理器"""
    
    def get_process_config(self, project_name: str) -> List[Dict]:
        """获取工序配置"""
        pass
    
    def create_process(self, project_name: str, process: Dict) -> str:
        """创建工序"""
        pass
    
    def update_process(self, process_id: str, process: Dict) -> bool:
        """更新工序"""
        pass
    
    def delete_process(self, process_id: str) -> bool:
        """删除工序"""
        pass
    
    def reorder_processes(self, project_name: str, process_ids: List[str]) -> bool:
        """调整工序顺序"""
        pass
```

### 3.5 数据访问层 (data_access_layer.py)

#### 主要功能
- 数据库操作封装
- 事务管理
- 连接池管理

#### 核心类

```python
class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        """建立数据库连接"""
        pass
    
    def execute(self, sql: str, params: tuple = None) -> Any:
        """执行SQL语句"""
        pass
    
    def query(self, sql: str, params: tuple = None) -> List[Dict]:
        """查询数据"""
        pass
    
    def transaction(self, operations: List[Callable]) -> bool:
        """执行事务"""
        pass
```

---

## 开发规范

### 4.1 代码风格

#### Python代码规范
- 遵循 PEP 8 规范
- 使用4个空格缩进
- 最大行长度120字符
- 使用类型提示

**示例：**
```python
from typing import Optional, List, Dict

def get_user_by_id(user_id: str) -> Optional[Dict]:
    """
    根据用户ID获取用户信息
    
    Args:
        user_id: 用户ID
        
    Returns:
        用户信息字典，如果不存在返回None
    """
    # 实现代码
    pass
```

#### JavaScript代码规范
- 使用ES6+语法
- 使用2个空格缩进
- 使用分号结尾
- 使用const/let，避免var

**示例：**
```javascript
const getUserById = async (userId) => {
  try {
    const response = await fetch(`/api/users/${userId}`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching user:', error);
    return null;
  }
};
```

### 4.2 命名规范

#### Python命名
- 类名：PascalCase (例如：`UserManager`)
- 函数名：snake_case (例如：`get_user_by_id`)
- 常量：UPPER_SNAKE_CASE (例如：`MAX_FILE_SIZE`)
- 私有方法：前缀下划线 (例如：`_internal_method`)

#### JavaScript命名
- 类名：PascalCase (例如：`PhotoManager`)
- 函数名：camelCase (例如：`getUserById`)
- 常量：UPPER_SNAKE_CASE (例如：`API_BASE_URL`)

### 4.3 注释规范

#### 文档字符串
```python
def upload_photo(file_path: str, metadata: Dict) -> Optional[int]:
    """
    上传工序照片
    
    Args:
        file_path: 照片文件路径
        metadata: 照片元数据，包含产品序列号、工序名称等
        
    Returns:
        照片ID，上传失败返回None
        
    Raises:
        ValueError: 文件路径无效
        IOError: 文件读取失败
        
    Example:
        >>> metadata = {'product_serial': 'PROD001', 'process_step': '热套工序'}
        >>> photo_id = upload_photo('/path/to/photo.jpg', metadata)
        >>> print(photo_id)
        123
    """
    pass
```

#### 行内注释
```python
# 检查用户权限
if not check_permission(user_id, 'photos', 'upload'):
    return {'error': '权限不足'}, 403

# 生成唯一文件名：产品序列号_工序名称_时间戳.jpg
filename = f"{product_serial}_{process_step}_{timestamp}.jpg"
```

### 4.4 错误处理

#### 统一错误处理
```python
from error_handler import handle_error, AppError

@app.route('/api/users/<user_id>')
def get_user(user_id):
    try:
        user = user_service.get_user(user_id)
        if not user:
            raise AppError('USER_NOT_FOUND', '用户不存在', 404)
        return jsonify({'success': True, 'data': user})
    except AppError as e:
        return handle_error(e)
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        return handle_error(AppError('INTERNAL_ERROR', '内部服务器错误', 500))
```

### 4.5 日志规范

```python
import logging

logger = logging.getLogger(__name__)

# DEBUG: 详细的调试信息
logger.debug(f'Processing photo upload: {filename}')

# INFO: 一般信息
logger.info(f'User {username} logged in successfully')

# WARNING: 警告信息
logger.warning(f'Disk space low: {free_space}MB remaining')

# ERROR: 错误信息
logger.error(f'Failed to upload photo: {error}')

# CRITICAL: 严重错误
logger.critical(f'Database connection lost')
```

---

## 测试指南

### 5.1 单元测试

#### 测试框架
- Python: pytest
- JavaScript: Jest

#### 编写测试
```python
# tests/test_permission_service.py
import pytest
from permission_service import PermissionService

class TestPermissionService:
    
    @pytest.fixture
    def service(self):
        return PermissionService()
    
    def test_admin_has_all_permissions(self, service):
        """测试管理员拥有所有权限"""
        user = {'id': '1', 'role': 'admin'}
        assert service.check_permission(user, 'records', 'delete') == True
    
    def test_user_cannot_delete(self, service):
        """测试普通用户无删除权限"""
        user = {'id': '2', 'role': 'user'}
        assert service.check_permission(user, 'records', 'delete') == False
```

#### 运行测试
```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_permission_service.py

# 运行特定测试
pytest tests/test_permission_service.py::TestPermissionService::test_admin_has_all_permissions

# 显示覆盖率
pytest --cov=app_web tests/
```

### 5.2 集成测试

```python
# tests/test_integration.py
import pytest
from mesapp import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_login_flow(client):
    """测试登录流程"""
    # 登录
    response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': 'testpass'
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] == True
    
    # 获取当前用户
    response = client.get('/api/auth/current-user')
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['username'] == 'testuser'
```

### 5.3 API测试

使用Postman或curl进行API测试

```bash
# 测试登录
curl -X POST http://localhost:8891/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}'

# 测试获取项目列表
curl -X GET http://localhost:8891/api/projects \
  -H "Cookie: session=<session_id>"

# 测试上传照片
curl -X POST http://localhost:8891/api/photos/upload \
  -H "Cookie: session=<session_id>" \
  -F "file=@photo.jpg" \
  -F "productSerial=PROD001" \
  -F "processStep=热套工序"
```

---

## 部署流程

### 6.1 开发环境部署

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库
python initialize_system.py

# 3. 启动开发服务器
python mesapp.py
```

### 6.2 生产环境部署

```bash
# 1. 上传代码到服务器
scp -r app_web user@server:/volume2/MES/

# 2. 使用部署脚本
cd app_web/deployment
chmod +x deploy.sh
./deploy.sh

# 3. 验证部署
curl http://172.16.30.2:8891/api/h2/health
```

### 6.3 Docker部署（可选）

```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app_web/ .

EXPOSE 8891

CMD ["python", "mesapp.py"]
```

```bash
# 构建镜像
docker build -t mes-system:latest .

# 运行容器
docker run -d -p 8891:8891 \
  -v /volume2/MES/data:/app/data \
  -v /volume2/MES/files:/app/files \
  --name mesapp \
  mes-system:latest
```

---

## 扩展开发

### 7.1 添加新的API端点

```python
# 在mesapp.py中添加
@app.route('/api/custom/endpoint', methods=['POST'])
@login_required
def custom_endpoint():
    """自定义API端点"""
    try:
        data = request.get_json()
        # 处理逻辑
        result = process_custom_data(data)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f'Error in custom endpoint: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500
```

### 7.2 添加新的权限规则

```python
# 在permission_service.py中扩展
PERMISSION_MATRIX = {
    'admin': {
        'records': ['create', 'read', 'update', 'delete'],
        'photos': ['create', 'read', 'update', 'delete'],
        'custom_resource': ['create', 'read', 'update', 'delete'],  # 新增
    },
    'user': {
        'records': ['create', 'read'],
        'photos': ['create', 'read'],
        'custom_resource': ['read'],  # 新增
    }
}
```

### 7.3 添加新的数据库表

```sql
-- 在database_setup.sql中添加
CREATE TABLE IF NOT EXISTS custom_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_custom_table_name ON custom_table(name);
```

### 7.4 添加新的前端页面

```html
<!-- templates/admin/custom_page.html -->
{% extends "base.html" %}

{% block title %}自定义页面{% endblock %}

{% block content %}
<div class="container">
    <h1>自定义功能</h1>
    <!-- 页面内容 -->
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/custom-page.js') }}"></script>
{% endblock %}
```

---

## 附录

### A. 常用工具

- **代码格式化：** black, autopep8
- **代码检查：** pylint, flake8
- **类型检查：** mypy
- **API测试：** Postman, curl
- **数据库工具：** DB Browser for SQLite

### B. 参考资源

- Flask文档：https://flask.palletsprojects.com/
- SQLite文档：https://www.sqlite.org/docs.html
- Python最佳实践：https://docs.python-guide.org/

### C. 版本控制

```bash
# 创建功能分支
git checkout -b feature/new-feature

# 提交代码
git add .
git commit -m "feat: add new feature"

# 推送到远程
git push origin feature/new-feature

# 创建Pull Request
```

---

**文档版本：** 1.0  
**更新日期：** 2025年1月15日  
**维护团队：** 开发部门
