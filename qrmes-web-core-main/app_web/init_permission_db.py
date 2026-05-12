#!/usr/bin/env python3
"""Initialize web_users.db with a default admin account."""

from __future__ import annotations

import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

from qrmes_shared_core.config import config


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_DISPLAY_NAME = "系统管理员"


def resolve_data_dir() -> Path:
    if not config.use_webdav:
        return Path(config.nas_local_base_path)
    return Path(__file__).resolve().parent.parent / "app" / "files"


def init_database(
    db_path: Path,
    admin_username: str = DEFAULT_ADMIN_USERNAME,
    admin_display_name: str = DEFAULT_ADMIN_DISPLAY_NAME,
) -> bool:
    print(f"正在初始化权限数据库: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                synology_username VARCHAR(100) UNIQUE NOT NULL,
                display_name VARCHAR(200),
                role VARCHAR(20) DEFAULT 'user' CHECK(role IN ('admin', 'user')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS permission_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(36),
                action VARCHAR(100),
                resource VARCHAR(200),
                result VARCHAR(20) CHECK(result IN ('allowed', 'denied')),
                ip_address VARCHAR(45),
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_synology_username ON users(synology_username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_logs_user_id ON permission_logs(user_id)")

        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        if admin_count == 0:
            admin_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO users (id, synology_username, display_name, role, created_at)
                VALUES (?, ?, ?, 'admin', ?)
                """,
                (admin_id, admin_username, admin_display_name, datetime.now().isoformat()),
            )
            print("已创建默认管理员账户")
            print(f"  用户名: {admin_username}")
            print(f"  显示名: {admin_display_name}")
            print(f"  ID: {admin_id}")
        else:
            print(f"数据库中已存在 {admin_count} 个管理员账户")

        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM permission_logs")
        log_count = cursor.fetchone()[0]
        print("\n数据库初始化完成:")
        print(f"  用户数: {user_count}")
        print(f"  权限日志数: {log_count}")
        print(f"  数据库路径: {db_path}")
        return True
    except Exception as exc:
        print(f"数据库初始化失败: {exc}")
        conn.rollback()
        return False
    finally:
        conn.close()


def main() -> int:
    print("=" * 60)
    print("权限数据库初始化工具")
    print("=" * 60)

    data_dir = resolve_data_dir()
    db_path = data_dir / "web_users.db"
    print(f"数据目录: {data_dir}")
    print(f"数据库路径: {db_path}")

    admin_username = sys.argv[1] if len(sys.argv) > 1 else (input(f"\n请输入管理员用户名（默认 {DEFAULT_ADMIN_USERNAME}）: ").strip() or DEFAULT_ADMIN_USERNAME)
    admin_display_name = sys.argv[2] if len(sys.argv) > 2 else (input(f"请输入管理员显示名（默认 {DEFAULT_ADMIN_DISPLAY_NAME}）: ").strip() or DEFAULT_ADMIN_DISPLAY_NAME)

    print("\n将创建管理员账户:")
    print(f"  用户名: {admin_username}")
    print(f"  显示名: {admin_display_name}")
    confirm = input("\n确认初始化数据库? (y/N): ").strip().lower()
    if confirm != "y":
        print("\n已取消初始化")
        return 0

    success = init_database(db_path, admin_username, admin_display_name)
    if success:
        print("\n数据库初始化成功")
        return 0
    print("\n数据库初始化失败")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
