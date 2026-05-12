"""
数据库架构定义模块
定义用户权限管理和工序记录相关的数据库表结构
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional
import time

logger = logging.getLogger(__name__)


class DatabaseSchema:
    """数据库架构管理器"""
    
    @staticmethod
    def create_user_permission_tables(conn: sqlite3.Connection) -> bool:
        """创建用户权限管理相关表"""
        try:
            # 用户表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    synology_username TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    role TEXT DEFAULT 'user' CHECK (role IN ('admin', 'user')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_login_at INTEGER
                )
            """)
            
            # 权限操作日志表
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
            
            # 创建用户表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_synology_username ON users(synology_username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_last_login ON users(last_login_at)")
            
            # 创建权限日志表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_permission_logs_user_id ON permission_logs(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_permission_logs_action ON permission_logs(action)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_permission_logs_created_at ON permission_logs(created_at)")
            
            conn.commit()
            logger.info("✓ 用户权限管理表创建完成")
            return True
            
        except Exception as e:
            logger.error(f"创建用户权限管理表失败: {e}")
            return False
    
    @staticmethod
    def create_process_recording_tables(conn: sqlite3.Connection) -> bool:
        """创建工序记录相关表"""
        try:
            # 工序照片表
            # 注意: captured_by 存储的是操作员用户名（非 users.id），不使用外键约束
            conn.execute("""
                CREATE TABLE IF NOT EXISTS process_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_serial TEXT NOT NULL,
                    process_step TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    captured_by TEXT,
                    captured_at INTEGER NOT NULL,
                    uploaded_at INTEGER,
                    metadata TEXT
                )
            """)
            
            # 工序配置表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS process_configurations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    order_index INTEGER DEFAULT 0,
                    required INTEGER DEFAULT 1,
                    photo_required INTEGER DEFAULT 1,
                    estimated_duration INTEGER DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            
            # 创建工序照片表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_process_photos_product_serial ON process_photos(product_serial)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_process_photos_process_step ON process_photos(process_step)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_process_photos_captured_by ON process_photos(captured_by)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_process_photos_captured_at ON process_photos(captured_at)")
            
            # 创建工序配置表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_process_configurations_order_index ON process_configurations(order_index)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_process_configurations_name ON process_configurations(name)")
            
            conn.commit()
            logger.info("✓ 工序记录表创建完成")
            return True
            
        except Exception as e:
            logger.error(f"创建工序记录表失败: {e}")
            return False
    
    @staticmethod
    def _migrate_process_photos_remove_fk(conn: sqlite3.Connection) -> bool:
        """迁移 process_photos 表：移除 captured_by 外键约束

        旧表有 FOREIGN KEY (captured_by) REFERENCES users(id)，
        但 Android 端传的是用户名而非 users.id，导致 INSERT 失败。
        """
        try:
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='process_photos'"
            )
            row = cursor.fetchone()
            if row is None:
                return True  # 表不存在，无需迁移

            create_sql = row[0] if isinstance(row, tuple) else row
            if 'FOREIGN KEY' not in create_sql:
                return True  # 已经没有外键，无需迁移

            logger.info("[迁移] process_photos 表检测到外键约束，开始迁移...")

            # 读取现有数据
            cursor = conn.execute("SELECT * FROM process_photos")
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            logger.info(f"[迁移] 读取 {len(rows)} 条照片记录")

            # 删除旧表，创建新表（无外键）
            conn.execute("DROP TABLE process_photos")
            conn.execute("""
                CREATE TABLE process_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_serial TEXT NOT NULL,
                    process_step TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    captured_by TEXT,
                    captured_at INTEGER NOT NULL,
                    uploaded_at INTEGER,
                    metadata TEXT
                )
            """)

            # 恢复数据
            if rows:
                placeholders = ', '.join(['?'] * len(columns))
                col_names = ', '.join(columns)
                conn.executemany(
                    f"INSERT INTO process_photos ({col_names}) VALUES ({placeholders})",
                    [tuple(row) for row in rows]
                )

            conn.commit()
            logger.info(f"[迁移] ✓ process_photos 表迁移完成，恢复 {len(rows)} 条记录")
            return True

        except Exception as e:
            logger.error(f"[迁移] ✗ process_photos 迁移失败: {e}")
            return False

    @staticmethod
    def initialize_all_tables(db_path: Path) -> bool:
        """初始化所有数据库表"""
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)

            with sqlite3.connect(db_path, timeout=10) as conn:
                # 启用 WAL 模式和优化设置
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=5000")
                # 注意：不开启 foreign_keys，因为 process_photos.captured_by 存的是用户名

                # 迁移旧的 process_photos 表（移除外键约束）
                DatabaseSchema._migrate_process_photos_remove_fk(conn)

                # 创建用户权限管理表
                if not DatabaseSchema.create_user_permission_tables(conn):
                    return False

                # 创建工序记录表
                if not DatabaseSchema.create_process_recording_tables(conn):
                    return False

                logger.info("✓ 所有数据库表初始化完成")
                return True

        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            return False
    
    @staticmethod
    def create_default_admin_user(db_path: Path, admin_username: str = "admin") -> bool:
        """创建默认管理员用户"""
        try:
            with sqlite3.connect(db_path, timeout=10) as conn:
                current_time = int(time.time() * 1000)
                
                # 检查是否已存在管理员用户
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin'",
                )
                admin_count = cursor.fetchone()[0]
                
                if admin_count == 0:
                    # 创建默认管理员用户
                    import uuid
                    admin_id = str(uuid.uuid4())
                    
                    conn.execute("""
                        INSERT INTO users (id, synology_username, display_name, role, created_at, updated_at)
                        VALUES (?, ?, ?, 'admin', ?, ?)
                    """, (admin_id, admin_username, "系统管理员", current_time, current_time))
                    
                    conn.commit()
                    logger.info(f"✓ 创建默认管理员用户: {admin_username}")
                    return True
                else:
                    logger.info("管理员用户已存在，跳过创建")
                    return True
                    
        except Exception as e:
            logger.error(f"创建默认管理员用户失败: {e}")
            return False