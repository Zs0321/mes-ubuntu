"""
本地用户管理服务模块
实现群晖账户到本地用户的映射逻辑，提供用户角色分配和管理功能
"""

import sqlite3
import logging
import time
import uuid
import hashlib
import threading
from typing import Optional, Dict, List, Any, TYPE_CHECKING, Set
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum

from synology_auth_client import SynologyAuthService, AuthResult, UserInfo

if TYPE_CHECKING:
    from permission_service import PermissionService

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_PASSWORD = "Ab123###"


class UserRole(Enum):
    """用户角色枚举"""
    ADMIN = 'admin'
    USER = 'user'


@dataclass
class LocalUser:
    """本地用户数据模型"""
    id: str
    synology_username: str
    display_name: str
    role: UserRole
    created_at: int
    updated_at: int
    last_login_at: Optional[int] = None
    email: Optional[str] = None
    local_password: Optional[str] = None
    password_hash: Optional[str] = None
    must_change_password: bool = True
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['role'] = self.role.value
        data['must_change_password'] = bool(self.must_change_password)
        data['is_active'] = bool(self.is_active)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LocalUser':
        """从字典创建对象"""
        data['role'] = UserRole(data['role'])
        data['must_change_password'] = bool(data.get('must_change_password', True))
        data['is_active'] = bool(data.get('is_active', True))
        return cls(**data)


@dataclass
class LocalGroup:
    """本地群组数据模型"""
    id: str
    synology_group_id: int
    name: str
    display_name: Optional[str]
    description: Optional[str]
    created_at: int
    updated_at: int

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class PermissionLog:
    """权限操作日志数据模型"""
    id: Optional[int]
    user_id: str
    action: str
    resource: str
    result: str  # 'allowed' or 'denied'
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: int


class UserManagementService:
    """本地用户管理服务"""
    _INIT_LOCK = threading.Lock()
    _INITIALIZED_PATHS: Set[str] = set()
    
    def __init__(self, db_path: Path, synology_auth_service: SynologyAuthService):
        """
        初始化用户管理服务
        
        Args:
            db_path: 数据库文件路径
            synology_auth_service: 群晖认证服务实例
        """
        self.db_path = db_path
        self.synology_auth = synology_auth_service
        self._ensure_database_once()
        
        logger.info(f"用户管理服务初始化完成: {db_path}")

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256((password or '').encode('utf-8')).hexdigest()
    
    def _connect(self) -> sqlite3.Connection:
        """????? SQLite ?????????? WAL ????? I/O ???"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_database_once(self):
        path_key = str(self.db_path)
        if path_key in self._INITIALIZED_PATHS:
            return
        with self._INIT_LOCK:
            if path_key in self._INITIALIZED_PATHS:
                return
            self._ensure_database()
            self._INITIALIZED_PATHS.add(path_key)

    def _ensure_database(self):
        """确保数据库和表存在"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self._connect() as conn:
                # 启用外键约束和优化设置
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=30000")
                
                # 创建用户表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        synology_username TEXT UNIQUE NOT NULL,
                        display_name TEXT,
                        role TEXT DEFAULT 'user' CHECK (role IN ('admin', 'user')),
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        last_login_at INTEGER,
                        email TEXT,
                        local_password TEXT,
                        password_hash TEXT,
                        must_change_password INTEGER DEFAULT 1,
                        is_active INTEGER DEFAULT 1
                    )
                """)
                
                # 创建权限日志表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS permission_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        action TEXT NOT NULL,
                        resource TEXT NOT NULL,
                        result TEXT NOT NULL CHECK (result IN ('allowed', 'denied')),
                        ip_address TEXT,
                        user_agent TEXT,
                        created_at INTEGER NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """)
                
                # 创建群组表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS groups (
                        id TEXT PRIMARY KEY,
                        synology_group_id INTEGER,
                        name TEXT UNIQUE NOT NULL,
                        display_name TEXT,
                        description TEXT,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_groups (
                        user_id TEXT NOT NULL,
                        group_id TEXT NOT NULL,
                        PRIMARY KEY (user_id, group_id),
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS group_permissions (
                        id TEXT PRIMARY KEY,
                        group_id TEXT NOT NULL,
                        permission TEXT NOT NULL,
                        effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
                        UNIQUE (group_id, permission)
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_permissions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        permission TEXT NOT NULL,
                        effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        UNIQUE (user_id, permission)
                    )
                """)

                # 创建索引
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_users_synology_username ON users(synology_username)",
                    "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
                    "CREATE INDEX IF NOT EXISTS idx_users_last_login ON users(last_login_at)",
                    "CREATE INDEX IF NOT EXISTS idx_permission_logs_user_id ON permission_logs(user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_permission_logs_action ON permission_logs(action)",
                    "CREATE INDEX IF NOT EXISTS idx_permission_logs_created_at ON permission_logs(created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_groups_synology_group_id ON groups(synology_group_id)",
                    "CREATE INDEX IF NOT EXISTS idx_user_groups_user ON user_groups(user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_user_groups_group ON user_groups(group_id)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_group_permissions_unique ON group_permissions(group_id, permission)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_permissions_unique ON user_permissions(user_id, permission)"
                ]
                
                for index_sql in indexes:
                    conn.execute(index_sql)
                
                # 数据库迁移：检查并添加缺失的列
                self._migrate_database(conn)

                conn.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")
                
                conn.commit()
                logger.info("数据库表和索引创建完成")
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    def _migrate_database(self, conn: sqlite3.Connection):
        """
        数据库迁移：检查并添加缺失的列
        
        Args:
            conn: 数据库连接对象
        """
        try:
            # 获取users表的列信息
            cursor = conn.execute("PRAGMA table_info(users)")
            columns = {row[1] for row in cursor.fetchall()}
            
            # 检查email列是否存在
            if 'email' not in columns:
                logger.info("检测到旧版数据库，正在添加 email 列...")
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
                logger.info("✓ 数据库迁移完成：已添加 email 列")

            if 'local_password' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN local_password TEXT")

            if 'password_hash' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

            if 'must_change_password' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 1")

            if 'is_active' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")

            default_hash = self.hash_password(DEFAULT_LOCAL_PASSWORD)
            conn.execute(
                """
                UPDATE users
                SET local_password = COALESCE(NULLIF(local_password, ''), ?),
                    password_hash = COALESCE(NULLIF(password_hash, ''), ?),
                    must_change_password = COALESCE(must_change_password, 1),
                    is_active = COALESCE(is_active, 1)
                WHERE local_password IS NULL
                   OR local_password = ''
                   OR password_hash IS NULL
                   OR password_hash = ''
                   OR must_change_password IS NULL
                   OR is_active IS NULL
                """,
                (DEFAULT_LOCAL_PASSWORD, default_hash)
            )

            self._ensure_group_tables(conn)
                
        except Exception as e:
            logger.warning(f"数据库迁移检查失败（可忽略）: {e}")

    def _ensure_group_tables(self, conn: sqlite3.Connection):
        """确保群组相关表存在"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                synology_group_id INTEGER,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                description TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_groups (
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                PRIMARY KEY (user_id, group_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
            )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_synology_group_id ON groups(synology_group_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_groups_user ON user_groups(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_groups_group ON user_groups(group_id)")
    
    def authenticate_and_map_user(self, username: str, password: str) -> Optional[LocalUser]:
        """
        认证群晖用户并映射到本地用户
        
        Args:
            username: 群晖用户名
            password: 密码
            
        Returns:
            LocalUser对象或None（认证失败）
        """
        logger.info(f"开始认证并映射用户: {username}")
        
        # 使用群晖认证服务进行认证
        auth_result = self.synology_auth.authenticate(username, password)
        
        if not auth_result.success:
            logger.warning(f"群晖认证失败: {username} - {auth_result.error}")
            return None
        
        # 认证成功，获取或创建本地用户
        local_user = self.get_user_by_synology_username(username)
        
        if local_user:
            # 更新最后登录时间
            self._update_last_login(local_user.id)
            logger.info(f"现有用户登录: {username}")
        else:
            # 创建新的本地用户
            local_user = self._create_local_user_from_synology(username, auth_result.user_info)
            if local_user:
                logger.info(f"创建新用户: {username}")
            else:
                logger.error(f"创建本地用户失败: {username}")
                return None
        
        return local_user

    def authenticate_local_user(
        self,
        username: str,
        password: str,
        allow_password_change_required: bool = False,
    ) -> tuple[Optional[LocalUser], Optional[str]]:
        username = (username or '').strip()
        password = password or ''

        if not username or not password:
            return None, "用户名或密码不能为空"

        local_user = self.get_user_by_synology_username(username)
        if not local_user:
            return None, "用户未在用户管理中启用"

        if not local_user.is_active:
            return None, "用户已被禁用"

        expected_hash = local_user.password_hash or self.hash_password(local_user.local_password or '')
        password_matches = (
            local_user.local_password == password
            or expected_hash == self.hash_password(password)
        )
        if not password_matches:
            return None, "用户名或密码错误"

        if local_user.must_change_password and not allow_password_change_required:
            return None, "首次登录请先修改密码"

        self._update_last_login(local_user.id)
        return self.get_user_by_id(local_user.id) or local_user, None

    def set_user_password(
        self,
        user_id: str,
        new_password: str,
        *,
        must_change_password: bool = False,
        is_active: Optional[bool] = None,
    ) -> bool:
        new_password = (new_password or '').strip()
        if len(new_password) < 4:
            return False

        try:
            current_time = int(time.time() * 1000)
            password_hash = self.hash_password(new_password)
            with self._connect() as conn:
                if is_active is None:
                    conn.execute(
                        """
                        UPDATE users
                        SET local_password = ?, password_hash = ?, must_change_password = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (new_password, password_hash, 1 if must_change_password else 0, current_time, user_id)
                    )
                else:
                    conn.execute(
                        """
                        UPDATE users
                        SET local_password = ?, password_hash = ?, must_change_password = ?, is_active = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (new_password, password_hash, 1 if must_change_password else 0, 1 if is_active else 0, current_time, user_id)
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"设置用户密码失败 (user_id={user_id}): {e}")
            return False

    def change_user_password(self, username: str, current_password: str, new_password: str) -> tuple[Optional[LocalUser], Optional[str]]:
        user, error = self.authenticate_local_user(username, current_password, allow_password_change_required=True)
        if not user:
            return None, error

        new_password = (new_password or '').strip()
        if len(new_password) < 4:
            return None, "新密码长度至少为 4 位"
        if new_password == current_password:
            return None, "新密码不能与当前密码相同"
        if not self.set_user_password(user.id, new_password, must_change_password=False):
            return None, "修改密码失败"
        return self.get_user_by_id(user.id) or user, None
    
    def get_or_create_user_by_smb(self, username: str, is_admin: bool = False) -> Optional[LocalUser]:
        """
        通过SMB认证后获取或创建本地用户（不依赖群晖API）
        
        Args:
            username: 用户名
            is_admin: 是否为管理员
            
        Returns:
            LocalUser对象或None
        """
        logger.info(f"通过SMB获取或创建用户: {username}, 管理员: {is_admin}")
        
        # 先尝试获取现有用户
        local_user = self.get_user_by_synology_username(username)
        
        if local_user:
            # 更新最后登录时间
            self._update_last_login(local_user.id)
            logger.info(f"现有用户登录: {username}")
            return local_user
        
        # 用户不存在，创建新用户
        try:
            current_time = int(time.time() * 1000)
            user_id = str(uuid.uuid4())
            
            role = UserRole.ADMIN if is_admin else UserRole.USER
            
            local_user = LocalUser(
                id=user_id,
                synology_username=username,
                display_name=username,
                role=role,
                created_at=current_time,
                updated_at=current_time,
                last_login_at=current_time,
                email=None,
                local_password=DEFAULT_LOCAL_PASSWORD,
                password_hash=self.hash_password(DEFAULT_LOCAL_PASSWORD),
                must_change_password=True,
                is_active=True
            )
            
            # 保存到数据库
            if self._save_user_to_db(local_user):
                logger.info(f"✓ 通过SMB成功创建本地用户: {username} (角色: {role.value})")
                return local_user
            else:
                logger.error(f"✗ 保存用户到数据库失败: {username}")
                return None
                
        except Exception as e:
            logger.error(f"创建本地用户异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _create_local_user_from_synology(self, synology_username: str, user_info: Optional[Dict[str, Any]]) -> Optional[LocalUser]:
        """
        从群晖用户信息创建本地用户
        
        Args:
            synology_username: 群晖用户名
            user_info: 群晖用户信息
            
        Returns:
            LocalUser对象或None
        """
        try:
            current_time = int(time.time() * 1000)
            user_id = str(uuid.uuid4())
            
            # 确定用户角色（默认为普通用户）
            role = UserRole.USER
            
            # 根据群晖用户信息中的is_admin字段确定角色
            if user_info and user_info.get('is_admin'):
                role = UserRole.ADMIN
            
            # 创建本地用户对象
            local_user = LocalUser(
                id=user_id,
                synology_username=synology_username,
                display_name=user_info.get('display_name', synology_username) if user_info else synology_username,
                role=role,
                created_at=current_time,
                updated_at=current_time,
                last_login_at=current_time,
                email=user_info.get('email') if user_info else None,
                local_password=DEFAULT_LOCAL_PASSWORD,
                password_hash=self.hash_password(DEFAULT_LOCAL_PASSWORD),
                must_change_password=True,
                is_active=True
            )
            
            # 保存到数据库
            if self._save_user_to_db(local_user):
                logger.info(f"成功创建本地用户: {synology_username} (角色: {role.value})")
                return local_user
            else:
                logger.error(f"保存本地用户到数据库失败: {synology_username}")
                return None
                
        except Exception as e:
            logger.error(f"创建本地用户异常: {e}")
            return None

    def create_local_user(
        self,
        username: str,
        *,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        role: UserRole | str = UserRole.USER,
        password: Optional[str] = None,
        must_change_password: bool = True,
        is_active: bool = True,
    ) -> tuple[Optional[LocalUser], Optional[str]]:
        """创建本地用户。"""
        username = (username or '').strip()
        if not username:
            return None, "用户名不能为空"

        existing = self.get_user_by_synology_username(username)
        if existing:
            return None, "用户已存在"

        role_value = role.value if isinstance(role, UserRole) else str(role or '').strip().lower()
        if role_value not in {UserRole.ADMIN.value, UserRole.USER.value}:
            return None, "无效的角色设置"

        initial_password = (password or '').strip() or DEFAULT_LOCAL_PASSWORD
        if len(initial_password) < 4:
            return None, "初始密码长度不能少于 4 位"

        current_time = int(time.time() * 1000)
        local_user = LocalUser(
            id=str(uuid.uuid4()),
            synology_username=username,
            display_name=(display_name or username).strip(),
            role=UserRole(role_value),
            created_at=current_time,
            updated_at=current_time,
            last_login_at=None,
            email=(email or '').strip() or None,
            local_password=initial_password,
            password_hash=self.hash_password(initial_password),
            must_change_password=bool(must_change_password),
            is_active=bool(is_active),
        )

        if not self._save_user_to_db(local_user):
            return None, "创建用户失败"

        created_user = self.get_user_by_synology_username(username)
        return created_user or local_user, None
    
    def _save_user_to_db(self, user: LocalUser) -> bool:
        """
        保存用户到数据库
        
        Args:
            user: LocalUser对象
            
        Returns:
            是否保存成功
        """
        try:
            with self._connect() as conn:
                existing = conn.execute(
                    """
                    SELECT id, created_at, local_password, password_hash, must_change_password, is_active
                    FROM users
                    WHERE synology_username = ?
                    """,
                    (user.synology_username,)
                ).fetchone()

                user_id = user.id
                created_at = user.created_at
                local_password = user.local_password
                password_hash = user.password_hash
                must_change_password = 1 if user.must_change_password else 0
                is_active = 1 if user.is_active else 0

                if existing:
                    user_id = existing[0]
                    created_at = existing[1]
                    if local_password is None:
                        local_password = existing[2]
                    if password_hash is None:
                        password_hash = existing[3]
                    if user.local_password is None and user.password_hash is None:
                        must_change_password = existing[4]
                    is_active = existing[5] if user.is_active is None else is_active

                conn.execute("""
                    INSERT INTO users
                    (id, synology_username, display_name, role, created_at, updated_at, last_login_at, email, local_password, password_hash, must_change_password, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(synology_username) DO UPDATE SET
                        display_name = excluded.display_name,
                        role = excluded.role,
                        updated_at = excluded.updated_at,
                        last_login_at = excluded.last_login_at,
                        email = excluded.email,
                        local_password = excluded.local_password,
                        password_hash = excluded.password_hash,
                        must_change_password = excluded.must_change_password,
                        is_active = excluded.is_active
                """, (
                    user_id,
                    user.synology_username,
                    user.display_name,
                    user.role.value,
                    created_at,
                    user.updated_at,
                    user.last_login_at,
                    user.email,
                    local_password,
                    password_hash or self.hash_password(local_password or DEFAULT_LOCAL_PASSWORD),
                    must_change_password,
                    is_active
                ))
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"保存用户到数据库失败: {e}")
            return False
    
    def _update_last_login(self, user_id: str) -> bool:
        """
        更新用户最后登录时间
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否更新成功
        """
        try:
            current_time = int(time.time() * 1000)
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                    (current_time, current_time, user_id)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"更新最后登录时间失败: {e}")
            return False

    def update_user_basic_info(self, user_id: str, display_name: Optional[str] = None, email: Optional[str] = None) -> bool:
        """更新用户基础信息（显示名、邮箱）"""
        try:
            fields = []
            params: List[Any] = []

            if display_name is not None:
                fields.append("display_name = ?")
                params.append(display_name)

            if email is not None:
                fields.append("email = ?")
                params.append(email)

            if not fields:
                # 没有需要更新的字段
                return True

            current_time = int(time.time() * 1000)
            fields.append("updated_at = ?")
            params.append(current_time)
            params.append(user_id)

            set_clause = ", ".join(fields)

            with self._connect() as conn:
                conn.execute(
                    f"UPDATE users SET {set_clause} WHERE id = ?",
                    params
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"更新用户基础信息失败 (user_id={user_id}): {e}")
            return False
    
    def update_user_role(self, user_id: str, role: UserRole | str) -> bool:
        """更新用户角色。"""
        try:
            role_value = role.value if isinstance(role, UserRole) else str(role).strip().lower()
            if role_value not in {UserRole.ADMIN.value, UserRole.USER.value}:
                logger.warning(f"无效的用户角色: {role}")
                return False

            current_time = int(time.time() * 1000)
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                    (role_value, current_time, user_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新用户角色失败 (user_id={user_id}, role={role}): {e}")
            return False

    def update_user_security_flags(
        self,
        user_id: str,
        *,
        must_change_password: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """更新首次改密与启用状态。"""
        try:
            fields = []
            params: List[Any] = []

            if must_change_password is not None:
                fields.append("must_change_password = ?")
                params.append(1 if must_change_password else 0)

            if is_active is not None:
                fields.append("is_active = ?")
                params.append(1 if is_active else 0)

            if not fields:
                return True

            current_time = int(time.time() * 1000)
            fields.append("updated_at = ?")
            params.append(current_time)
            params.append(user_id)

            with self._connect() as conn:
                cursor = conn.execute(
                    f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
                    params
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新用户安全标记失败 (user_id={user_id}): {e}")
            return False

    def update_user_role(self, user_id: str, role: UserRole | str) -> bool:
        """更新用户角色。"""
        try:
            role_value = role.value if isinstance(role, UserRole) else str(role).strip().lower()
            if role_value not in {UserRole.ADMIN.value, UserRole.USER.value}:
                logger.warning(f"无效的用户角色: {role}")
                return False

            current_time = int(time.time() * 1000)
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                    (role_value, current_time, user_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新用户角色失败 (user_id={user_id}, role={role}): {e}")
            return False

    def update_user_security_flags(
        self,
        user_id: str,
        *,
        must_change_password: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """更新首次改密与启用状态。"""
        try:
            fields = []
            params: List[Any] = []

            if must_change_password is not None:
                fields.append("must_change_password = ?")
                params.append(1 if must_change_password else 0)

            if is_active is not None:
                fields.append("is_active = ?")
                params.append(1 if is_active else 0)

            if not fields:
                return True

            current_time = int(time.time() * 1000)
            fields.append("updated_at = ?")
            params.append(current_time)
            params.append(user_id)

            with self._connect() as conn:
                cursor = conn.execute(
                    f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
                    params
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新用户安全标记失败 (user_id={user_id}): {e}")
            return False

    def delete_user(self, user_id: str) -> bool:
        """删除本地用户。"""
        try:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除用户失败 (user_id={user_id}): {e}")
            return False

    def set_user_groups(self, user_id: str, group_ids: List[str]) -> int:
        """设置用户所属群组（覆盖式）"""
        return self._sync_user_to_groups(user_id, group_ids)
    
    def get_user_by_synology_username(self, synology_username: str) -> Optional[LocalUser]:
        """
        根据群晖用户名获取本地用户
        
        Args:
            synology_username: 群晖用户名
            
        Returns:
            LocalUser对象或None
        """
        try:
            with self._connect() as conn:
                # 容忍群组名称/描述中可能存在的非 UTF-8 文本
                conn.text_factory = lambda b: b.decode('utf-8', 'replace') if isinstance(b, (bytes, bytearray)) else b
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM users WHERE synology_username = ?",
                    (synology_username,)
                )
                row = cursor.fetchone()
                
                if row:
                    return LocalUser.from_dict(dict(row))
                return None
                
        except Exception as e:
            logger.error(f"查询用户失败: {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[LocalUser]:
        """
        根据用户ID获取本地用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            LocalUser对象或None
        """
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    return LocalUser.from_dict(dict(row))
                return None
                
        except Exception as e:
            logger.error(f"查询用户失败: {e}")
            return None
    
    def get_all_users(self) -> List[LocalUser]:
        """获取所有本地用户"""
        try:
            with self._connect() as conn:
                # 容忍历史数据中可能存在的非 UTF-8 文本，防止页面加载时抛出解码异常
                conn.text_factory = lambda b: b.decode('utf-8', 'replace') if isinstance(b, (bytes, bytearray)) else b
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM users ORDER BY created_at DESC")

                users: List[LocalUser] = []
                for row in cursor.fetchall():
                    users.append(LocalUser(
                        id=row['id'],
                        synology_username=row['synology_username'],
                        display_name=row['display_name'],
                        role=UserRole(row['role']),
                        created_at=row['created_at'],
                        updated_at=row['updated_at'],
                        last_login_at=row['last_login_at'],
                        email=row['email'],
                        local_password=row['local_password'] if 'local_password' in row.keys() else None,
                        password_hash=row['password_hash'] if 'password_hash' in row.keys() else None,
                        must_change_password=bool(row['must_change_password']) if 'must_change_password' in row.keys() else True,
                        is_active=bool(row['is_active']) if 'is_active' in row.keys() else True
                    ))

                return users

        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []

    def get_group_by_id(self, group_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取群组"""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM groups WHERE id = ?", (group_id,)
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"获取群组失败: {e}")
            return None

    def get_all_groups(self, include_member_count: bool = True) -> List[Dict[str, Any]]:
        """获取所有群组

        Args:
            include_member_count: 是否在结果中附带成员数量统计
        """
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                if include_member_count:
                    cursor = conn.execute(
                        """
                        SELECT g.*, 
                               (SELECT COUNT(*) FROM user_groups ug WHERE ug.group_id = g.id) AS member_count
                        FROM groups g
                        ORDER BY g.name
                        """
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM groups ORDER BY name"
                    )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取群组列表失败: {e}")
            return []
    
    def _save_or_update_group(self, group_name: str, group_info: Dict[str, Any]) -> (Optional[str], bool):
        """保存或更新群组到数据库，返回群组ID及是否新建"""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                current_time = int(time.time() * 1000)

                cursor = conn.execute(
                    "SELECT id FROM groups WHERE name = ?",
                    (group_name,)
                )
                existing = cursor.fetchone()

                if existing:
                    group_id = existing['id']
                    conn.execute(
                        """
                        UPDATE groups
                        SET display_name = ?, description = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            group_info.get('display_name', group_name),
                            group_info.get('description', ''),
                            current_time,
                            group_id
                        )
                    )
                    logger.debug(f"更新群组: {group_name}")
                    created = False
                else:
                    group_id = str(uuid.uuid4())
                    synology_gid = group_info.get('gid', hash(group_name) % 100000)

                    conn.execute(
                        """
                        INSERT INTO groups (id, synology_group_id, name, display_name, description, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            group_id,
                            synology_gid,
                            group_name,
                            group_info.get('display_name', group_name),
                            group_info.get('description', ''),
                            current_time,
                            current_time
                        )
                    )
                    logger.debug(f"创建群组: {group_name}")
                    created = True

                conn.commit()
                return group_id, created

        except Exception as e:
            logger.error(f"保存群组 {group_name} 失败: {e}")
            return None, False

    def _sync_user_to_groups(self, user_id: str, group_ids: List[str]) -> int:
        """为用户建立群组关系映射，返回关联数量"""
        if not group_ids:
            return 0

        try:
            with self._connect() as conn:
                # 删除该用户现有的所有群组关系
                conn.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))

                # 批量插入新的群组关系
                insert_items = [(user_id, gid) for gid in group_ids]
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO user_groups (user_id, group_id)
                    VALUES (?, ?)
                    """,
                    insert_items
                )

                conn.commit()
                return len(insert_items)

        except Exception as e:
            logger.error(f"同步用户群组关系失败 (user_id={user_id}): {e}")
            return 0

    def _sync_group_members(self, group_id: str, members_data: Any) -> int:
        """同步群组成员映射到 user_groups 表，返回关联数量（已废弃，改用_sync_user_to_groups）"""
        if not members_data:
            return 0

        usernames = self._extract_member_usernames(members_data)
        if not usernames:
            return 0

        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("DELETE FROM user_groups WHERE group_id = ?", (group_id,))

                insert_items = []
                for username in usernames:
                    cursor = conn.execute(
                        "SELECT id FROM users WHERE synology_username = ?",
                        (username,)
                    )
                    row = cursor.fetchone()
                    if row:
                        insert_items.append((row['id'], group_id))
                    else:
                        logger.debug(f"群组成员 {username} 未找到对应本地用户，跳过映射")

                if insert_items:
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO user_groups (user_id, group_id)
                        VALUES (?, ?)
                        """,
                        insert_items
                    )

                conn.commit()
                return len(insert_items)

        except Exception as e:
            logger.error(f"同步群组成员失败 (group_id={group_id}): {e}")
            return 0

    def set_user_groups(self, user_id: str, group_ids: List[str]) -> int:
        """设置用户所属群组（覆盖式），返回关联数量"""
        try:
            normalized = [gid for gid in (group_ids or []) if isinstance(gid, str) and gid]
            return self._sync_user_to_groups(user_id, normalized)
        except Exception as e:
            logger.error(f"设置用户群组失败 (user_id={user_id}): {e}")
            return 0

    def _extract_member_usernames(self, members: Any) -> Set[str]:
        """从群组成员数据结构中提取用户名集合"""
        usernames: Set[str] = set()

        if not members:
            return usernames

        if isinstance(members, str):
            usernames.add(members)
        elif isinstance(members, dict):
            # DSM返回的结构通常包含 users 或 name/username 字段
            if 'users' in members:
                usernames.update(self._extract_member_usernames(members['users']))
            if 'name' in members and isinstance(members['name'], str):
                usernames.add(members['name'])
            if 'username' in members and isinstance(members['username'], str):
                usernames.add(members['username'])
        elif isinstance(members, list):
            for item in members:
                usernames.update(self._extract_member_usernames(item))

        return {name.strip() for name in usernames if isinstance(name, str) and name.strip()}

    def _extract_group_names(self, groups: Any) -> List[str]:
        """从用户信息中的群组数据结构中提取群组名称列表

        群晖返回的 groups 字段可能是：
        - 字符串（单个群组名）
        - 字典（包含 name 或 groupname 字段）
        - 列表（嵌套上述结构）
        - 或包含 groups 子字段的嵌套结构
        """
        names: Set[str] = set()

        if not groups:
            return []

        if isinstance(groups, str):
            names.add(groups)
        elif isinstance(groups, dict):
            if 'name' in groups and isinstance(groups['name'], str):
                names.add(groups['name'])
            if 'groupname' in groups and isinstance(groups['groupname'], str):
                names.add(groups['groupname'])
            if 'groups' in groups:
                nested = self._extract_group_names(groups['groups'])
                names.update(nested)
        elif isinstance(groups, list):
            for item in groups:
                nested = self._extract_group_names(item)
                names.update(nested)

        return [name.strip() for name in names if isinstance(name, str) and name.strip()]

    def get_groups_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户所属群组"""
        try:
            with self._connect() as conn:
                # 容忍用户群组关联中可能存在的非 UTF-8 文本
                conn.text_factory = lambda b: b.decode('utf-8', 'replace') if isinstance(b, (bytes, bytearray)) else b
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT g.id, g.synology_group_id, g.name, g.display_name
                    FROM groups g
                    INNER JOIN user_groups ug ON g.id = ug.group_id
                    WHERE ug.user_id = ?
                    ORDER BY g.name
                    """,
                    (user_id,)
                )

                groups = []
                for row in cursor.fetchall():
                    groups.append({
                        'id': row['id'],
                        'synology_group_id': row['synology_group_id'],
                        'name': row['name'],
                        'display_name': row['display_name']
                    })

                return groups

        except Exception as e:
            logger.error(f"获取用户群组失败: {e}")
            return []

    # ===== 权限配置相关方法 =====

    def get_effective_permissions(self, user_id: str, permission_service: Optional['PermissionService'] = None) -> Dict[str, Any]:
        """获取用户最终权限评估信息"""
        result = {
            'user_id': user_id,
            'role_permissions': set(),
            'group_permissions': {},
            'user_permissions': {},
            'effective_permissions': {}
        }

        user = self.get_user_by_id(user_id)
        if not user:
            return result

        if permission_service:
            role_perms = permission_service.get_user_permissions(user)
        else:
            role_perms = set()
        result['role_permissions'] = {perm.value for perm in role_perms}

        group_perms = self.get_group_permissions_for_user(user_id)
        result['group_permissions'] = group_perms

        user_perms = self.get_user_permissions_override(user_id)
        result['user_permissions'] = user_perms

        if permission_service:
            combined = permission_service.evaluate_permissions(user_id)
            result['effective_permissions'] = combined

        return result

    def get_user_permissions_override(self, user_id: str) -> Dict[str, str]:
        """获取用户显式权限配置"""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT permission, effect FROM user_permissions
                    WHERE user_id = ?
                    """,
                    (user_id,)
                )
                return {row['permission']: row['effect'] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"获取用户权限覆盖失败: {e}")
            return {}

    def get_group_permissions(self, group_id: str) -> Dict[str, str]:
        """获取群组显式权限配置"""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT permission, effect FROM group_permissions
                    WHERE group_id = ?
                    """,
                    (group_id,)
                )
                return {row['permission']: row['effect'] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"获取群组权限失败: {e}")
            return {}

    def get_group_permissions_for_user(self, user_id: str) -> Dict[str, Dict[str, str]]:
        """获取用户所属群组的权限配置"""
        group_permissions: Dict[str, Dict[str, str]] = {}
        groups = self.get_groups_for_user(user_id)
        for group in groups:
            group_permissions[group['id']] = self.get_group_permissions(group['id'])
        return group_permissions

    def get_group_permissions_for_user_with_source(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户所属群组的权限配置及来源信息

        返回结构示例：
        [
            {
                'group_id': '...',
                'synology_group_id': 123,
                'is_local': False,
                'permissions': { 'web:view_records': 'allow', ... }
            },
            ...
        ]
        """
        result: List[Dict[str, Any]] = []
        groups = self.get_groups_for_user(user_id)
        for group in groups:
            perms = self.get_group_permissions(group['id'])
            result.append({
                'group_id': group['id'],
                'synology_group_id': group.get('synology_group_id'),
                'is_local': group.get('synology_group_id') is None,
                'permissions': perms,
            })
        return result

    def create_local_group(self, name: str, display_name: Optional[str] = None, description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """创建本地群组（synology_group_id 为空）"""
        name = (name or '').strip()
        if not name:
            logger.error("创建群组失败: 名称不能为空")
            return None
        display_name = (display_name or name).strip()
        description = (description or '').strip()
        current_time = int(time.time() * 1000)
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT id FROM groups WHERE name = ?",
                    (name,)
                )
                if cursor.fetchone():
                    logger.warning(f"创建群组失败，名称已存在: {name}")
                    return None
                group_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO groups (id, synology_group_id, name, display_name, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (group_id, None, name, display_name, description, current_time, current_time)
                )
                conn.commit()
                return {
                    'id': group_id,
                    'synology_group_id': None,
                    'name': name,
                    'display_name': display_name,
                    'description': description,
                    'created_at': current_time,
                    'updated_at': current_time,
                    'member_count': 0
                }
        except Exception as e:
            logger.error(f"创建本地群组失败: {e}")
            return None

    def update_group(self, group_id: str, display_name: Optional[str] = None, description: Optional[str] = None) -> bool:
        """更新群组显示名和描述"""
        try:
            updates: List[str] = []
            params: List[Any] = []
            if display_name is not None:
                updates.append("display_name = ?")
                params.append(display_name.strip())
            if description is not None:
                updates.append("description = ?")
                params.append((description or '').strip())
            if not updates:
                return True
            current_time = int(time.time() * 1000)
            updates.append("updated_at = ?")
            params.append(current_time)
            params.append(group_id)
            with self._connect() as conn:
                cursor = conn.execute(
                    f"UPDATE groups SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新群组失败 (group_id={group_id}): {e}")
            return False

    def delete_group(self, group_id: str) -> bool:
        """删除群组（本地或同步来源均可）"""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT id FROM groups WHERE id = ?",
                    (group_id,)
                )
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"删除群组失败，群组不存在: {group_id}")
                    return False

                conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"删除群组失败 (group_id={group_id}): {e}")
            return False

    def get_group_members(self, group_id: str) -> List[Dict[str, Any]]:
        """获取群组成员列表"""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT u.id, u.synology_username, u.display_name, u.role, u.email, u.last_login_at
                    FROM users u
                    INNER JOIN user_groups ug ON u.id = ug.user_id
                    WHERE ug.group_id = ?
                    ORDER BY u.synology_username
                    """,
                    (group_id,)
                )
                members: List[Dict[str, Any]] = []
                for row in cursor.fetchall():
                    members.append({
                        'id': row['id'],
                        'synology_username': row['synology_username'],
                        'display_name': row['display_name'],
                        'role': row['role'],
                        'email': row['email'],
                        'last_login_at': row['last_login_at']
                    })
                return members
        except Exception as e:
            logger.error(f"获取群组成员失败 (group_id={group_id}): {e}")
            return []

    def update_group_members(self, group_id: str, add_user_ids: List[str], remove_user_ids: List[str]) -> Dict[str, int]:
        """增量更新群组成员，返回新增和移除数量"""
        add_user_ids = list({uid for uid in (add_user_ids or []) if uid})
        remove_user_ids = list({uid for uid in (remove_user_ids or []) if uid})
        added = 0
        removed = 0
        try:
            with self._connect() as conn:
                if remove_user_ids:
                    placeholders = ','.join(['?'] * len(remove_user_ids))
                    params = [group_id] + remove_user_ids
                    cursor = conn.execute(
                        f"DELETE FROM user_groups WHERE group_id = ? AND user_id IN ({placeholders})",
                        params
                    )
                    removed = cursor.rowcount or 0
                if add_user_ids:
                    insert_items = [(uid, group_id) for uid in add_user_ids]
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO user_groups (user_id, group_id)
                        VALUES (?, ?)
                        """,
                        insert_items
                    )
                    added = len(insert_items)
                conn.commit()
            return {'added': added, 'removed': removed}
        except Exception as e:
            logger.error(f"更新群组成员失败 (group_id={group_id}): {e}")
            return {'added': 0, 'removed': 0}

    def save_user_permissions(self, user_id: str, changes: Dict[str, str]) -> bool:
        """保存用户权限覆盖配置（增量更新）"""
        try:
            current_time = int(time.time() * 1000)
            with self._connect() as conn:
                for perm, effect in changes.items():
                    if effect in ('allow', 'deny'):
                        conn.execute(
                            """
                            INSERT INTO user_permissions (id, user_id, permission, effect, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(user_id, permission) DO UPDATE SET
                                effect = excluded.effect,
                                updated_at = excluded.updated_at
                            """,
                            (str(uuid.uuid4()), user_id, perm, effect, current_time, current_time),
                        )
                    else:
                        conn.execute(
                            "DELETE FROM user_permissions WHERE user_id = ? AND permission = ?",
                            (user_id, perm),
                        )

                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存用户权限失败: {e}")
            return False

    def save_group_permissions(self, group_id: str, changes: Dict[str, str]) -> bool:
        """保存群组权限配置（增量更新）"""
        try:
            current_time = int(time.time() * 1000)
            with self._connect() as conn:
                for perm, effect in changes.items():
                    if effect in ('allow', 'deny'):
                        conn.execute(
                            """
                            INSERT INTO group_permissions (id, group_id, permission, effect, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(group_id, permission) DO UPDATE SET
                                effect = excluded.effect,
                                updated_at = excluded.updated_at
                            """,
                            (str(uuid.uuid4()), group_id, perm, effect, current_time, current_time),
                        )
                    else:
                        conn.execute(
                            "DELETE FROM group_permissions WHERE group_id = ? AND permission = ?",
                            (group_id, perm),
                        )

                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存群组权限失败: {e}")
            return False

    def sync_users_from_synology(self, admin_username: str, admin_password: str, sync_groups: bool = False) -> Dict[str, Any]:
        """
        从群晖DSM同步用户和群组到本地数据库
        
        Args:
            admin_username: 群晖管理员账户
            admin_password: 管理员密码
            sync_groups: 是否同步群组信息
            
        Returns:
            同步结果字典，包含成功、失败计数等信息
        """
        logger.info(f"开始同步群晖用户 - 管理员: {admin_username}, 同步群组: {sync_groups}")
        
        result = {
            'success': False,
            'created': 0,
            'updated': 0,
            'failed': 0,
            'error': None,
            'groups_total': 0,
            'groups_created': 0,
            'groups_updated': 0,
            'groups_failed': 0
        }
        
        try:
            # 1. 获取所有用户列表（内部会自动处理管理员认证和登出）
            users_data = self.synology_auth.list_all_users(admin_username, admin_password)
            if not users_data:
                detail_error = getattr(self.synology_auth, 'last_error', None)
                if detail_error:
                    result['error'] = f"获取用户列表失败: {detail_error}"
                else:
                    result['error'] = "获取用户列表失败，请检查管理员账号密码"
                logger.error(result['error'])
                return result
            
            logger.info(f"✓ 获取到 {len(users_data)} 个用户")
            
            # 2. 同步用户到本地数据库（同时收集群组成员映射）
            user_group_mappings = []  # [(username, [group_names])]
            
            for user_info in users_data:
                try:
                    synology_username = user_info.get('username')
                    if not synology_username:
                        logger.warning(f"跳过无用户名的记录: {user_info}")
                        continue
                    
                    # 收集用户的群组信息（无论新旧用户都收集，后续根据现有本地群组判断是否作为初次导入）
                    raw_groups = user_info.get('groups', [])
                    group_names = self._extract_group_names(raw_groups)
                    if group_names:
                        user_group_mappings.append((synology_username, group_names))

                    # 检查用户是否已存在
                    existing_user = self.get_user_by_synology_username(synology_username)

                    if existing_user:
                        # 更新现有用户（角色/显示名等），不立即改群组关系（后面仅在用户当前没有本地群组时作为初次导入）
                        logger.info(f"更新用户: {synology_username}")
                        result['updated'] += 1
                    else:
                        # 创建新用户，后续为其建立群组关系作为初始导入
                        local_user = self._create_local_user_from_synology(synology_username, user_info)
                        if local_user:
                            logger.info(f"创建用户: {synology_username}")
                            result['created'] += 1
                        else:
                            logger.warning(f"创建用户失败: {synology_username}")
                            result['failed'] += 1
                            
                except Exception as e:
                    logger.error(f"同步用户 {user_info} 失败: {e}")
                    result['failed'] += 1
            
            # 3. 同步群组（如果需要）
            if sync_groups:
                try:
                    groups_data = self.synology_auth.list_all_groups(admin_username, admin_password)
                    if groups_data:
                        result['groups_total'] = len(groups_data)
                        logger.info(f"✓ 获取到 {len(groups_data)} 个群组")
                        
                        # 首先同步群组本身
                        group_name_to_id = {}  # {group_name: group_id}
                        logger.info(f"开始同步 {len(groups_data)} 个群组...")
                        for idx, group_info in enumerate(groups_data):
                            try:
                                group_name = group_info.get('name')
                                
                                if not group_name:
                                    logger.warning(f"跳过无名称的群组: {group_info}")
                                    continue
                                
                                group_id, created = self._save_or_update_group(group_name, group_info)

                                if not group_id:
                                    logger.warning(f"群组 {group_name} 保存失败，跳过")
                                    result['groups_failed'] += 1
                                    continue
                                
                                group_name_to_id[group_name] = group_id

                                if created:
                                    result['groups_created'] += 1
                                    logger.info(f"创建群组: {group_name}")
                                else:
                                    result['groups_updated'] += 1
                                
                                # 每处理10个群组输出一次进度
                                if (idx + 1) % 10 == 0:
                                    logger.info(f"群组同步进度: {idx + 1}/{len(groups_data)}")
                                
                            except Exception as e:
                                logger.error(f"同步群组 {group_info} 失败: {e}")
                                import traceback
                                logger.debug(traceback.format_exc())
                                result['groups_failed'] += 1

                        logger.info(f"✓ 群组同步完成 - 创建: {result['groups_created']}, 更新: {result['groups_updated']}, 失败: {result['groups_failed']}")

                        # 基于群组成员信息构建用户-群组映射（用户名 -> 群组名集合）
                        member_mappings: Dict[str, Set[str]] = {}
                        logger.info("开始从群组成员信息构建用户-群组映射...")
                        groups_with_members = 0
                        total_member_entries = 0
                        for group_info in groups_data:
                            group_name = group_info.get('name')
                            if not group_name:
                                continue

                            members_data = group_info.get('members')
                            if members_data:
                                groups_with_members += 1
                                # 调试：输出前几个群组的成员数据结构
                                if groups_with_members <= 3:
                                    logger.debug(f"群组 {group_name} 成员数据类型: {type(members_data).__name__}, 内容: {str(members_data)[:200]}")
                            
                            usernames = self._extract_member_usernames(members_data)
                            if not usernames:
                                continue

                            total_member_entries += len(usernames)
                            for username in usernames:
                                if not isinstance(username, str) or not username.strip():
                                    continue
                                username = username.strip()
                                if username not in member_mappings:
                                    member_mappings[username] = set()
                                member_mappings[username].add(group_name)
                        
                        logger.info(f"群组成员统计: {groups_with_members}/{len(groups_data)} 个群组有成员数据, 共提取 {total_member_entries} 个成员条目, 涉及 {len(member_mappings)} 个不同用户")

                        # 合并来自用户信息(user_info.groups)和群组成员(groups.members)的映射
                        if user_group_mappings:
                            merged: Dict[str, Set[str]] = {}
                            for username, group_names in user_group_mappings:
                                if not isinstance(username, str) or not username.strip():
                                    continue
                                u = username.strip()
                                if u not in merged:
                                    merged[u] = set()
                                for g in (group_names or []):
                                    if isinstance(g, str) and g.strip():
                                        merged[u].add(g.strip())

                            # 把群组成员信息合并进去
                            for username, group_names in member_mappings.items():
                                u = username.strip()
                                if u not in merged:
                                    merged[u] = set()
                                merged[u].update(group_names)
                        else:
                            merged = member_mappings

                        # 归一化为列表形式，供后续 user_groups 映射使用
                        user_group_mappings = [
                            (username, sorted(group_names))
                            for username, group_names in merged.items()
                        ]

                        # 然后根据用户的群组归属建立 user_groups 映射
                        # 注意：仅对“当前没有任何本地群组”的用户建立映射（包含新建用户和首次同步的旧用户），
                        # 避免覆盖已经在Web端调整过的本地群组配置。
                        logger.info(
                            "开始建立用户-群组映射关系，共 %s 个用户有群组信息（仅对当前无本地群组的用户执行初次导入）",
                            len(user_group_mappings),
                        )
                        total_mappings = 0
                        for username, group_names in user_group_mappings:
                            local_user = self.get_user_by_synology_username(username)
                            if not local_user:
                                logger.debug(f"用户 {username} 不存在，跳过群组映射")
                                continue

                            # 如果用户已经存在本地群组，则视为已做过本地调整，不再自动覆盖
                            existing_groups = self.get_groups_for_user(local_user.id)
                            if existing_groups:
                                logger.debug(
                                    "用户 %s 已存在 %s 个本地群组，跳过自动群组导入",
                                    username,
                                    len(existing_groups),
                                )
                                continue
                            
                            # 为该用户建立群组关系（初次导入）
                            valid_group_ids = []
                            for group_name in group_names:
                                if group_name in group_name_to_id:
                                    valid_group_ids.append(group_name_to_id[group_name])
                            
                            if valid_group_ids:
                                count = self._sync_user_to_groups(local_user.id, valid_group_ids)
                                total_mappings += count
                        
                        logger.info(f"✓ 用户-群组映射建立完成，共 {total_mappings} 条关系")
                        
                except Exception as e:
                    logger.error(f"同步群组失败: {e}")
            
            result['success'] = True
            logger.info(f"✓ 用户同步完成 - 创建: {result['created']}, 更新: {result['updated']}, 失败: {result['failed']}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"同步用户异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return result
