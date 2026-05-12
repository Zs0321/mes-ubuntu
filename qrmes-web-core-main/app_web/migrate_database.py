#!/usr/bin/env python3
"""
数据库迁移脚本
添加密码字段，支持本地认证
"""

import sqlite3
import hashlib
import sys
from pathlib import Path


def hash_password(password: str, salt: str = "") -> str:
    """密码哈希"""
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    return hash_obj.hexdigest()


def migrate_database(db_path: Path, default_admin_password: str = "admin123"):
    """
    执行数据库迁移
    
    Args:
        db_path: 数据库文件路径
        default_admin_password: 默认管理员密码
    """
    print(f"开始迁移数据库: {db_path}")
    
    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 如果数据库不存在，先创建基础表结构
    if not db_path.exists():
        print(f"数据库文件不存在，将创建新数据库: {db_path}")
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 创建基础用户表
            cursor.execute("""
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
            
            # 创建权限日志表
            cursor.execute("""
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
            
            conn.commit()
            conn.close()
            print("✓ 基础表结构创建成功")
        except Exception as e:
            print(f"✗ 创建基础表结构失败: {e}")
            return False
    
    # 备份数据库
    backup_path = db_path.with_suffix('.db.backup')
    print(f"备份数据库到: {backup_path}")
    
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print("✓ 数据库备份成功")
    except Exception as e:
        print(f"✗ 数据库备份失败: {e}")
        return False
    
    # 连接数据库
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 检查是否已经迁移
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'password_hash' in columns:
            print("数据库已经迁移过")
            
            # 检查是否有管理员
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            admin_count = cursor.fetchone()[0]
            
            if admin_count == 0:
                print("未找到管理员账户，将创建默认管理员...")
                # 继续执行以创建管理员
            else:
                print(f"已有 {admin_count} 个管理员账户，跳过迁移")
                conn.close()
                return True
        
        # 只在字段不存在时添加
        if 'password_hash' not in columns:
            print("开始添加密码字段...")
            
            # 添加密码字段
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN password_salt TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
            
            print("✓ 密码字段添加成功")
        else:
            print("密码字段已存在")
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")
        print("✓ 索引创建成功")
        
        # 检查是否有管理员账户
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            # 创建默认管理员
            print("未找到管理员账户，创建默认管理员...")
            import uuid
            import time
            
            admin_id = str(uuid.uuid4())
            current_time = int(time.time() * 1000)
            password_hash = hash_password(default_admin_password)
            
            cursor.execute("""
                INSERT INTO users 
                (id, synology_username, display_name, role, password_hash, password_salt, 
                 is_active, created_at, updated_at)
                VALUES (?, ?, ?, 'admin', ?, '', 1, ?, ?)
            """, (admin_id, 'admin', '系统管理员', password_hash, current_time, current_time))
            
            print(f"✓ 创建默认管理员账户: admin")
        else:
            # 为现有管理员设置密码
            password_hash = hash_password(default_admin_password)
            
            cursor.execute("""
                UPDATE users 
                SET password_hash = ?,
                    password_salt = '',
                    is_active = 1
                WHERE role = 'admin' AND password_hash IS NULL
            """, (password_hash,))
            
            updated_count = cursor.rowcount
            if updated_count > 0:
                print(f"✓ 为 {updated_count} 个管理员账户设置默认密码")
            else:
                print("✓ 管理员账户已有密码")
        
        # 提交更改
        conn.commit()
        
        # 显示迁移结果
        print("\n迁移后的用户列表:")
        cursor.execute("""
            SELECT 
                synology_username,
                display_name,
                role,
                CASE WHEN password_hash IS NOT NULL THEN '已设置' ELSE '未设置' END as password_status,
                CASE WHEN is_active = 1 THEN '启用' ELSE '禁用' END as status
            FROM users
        """)
        
        users = cursor.fetchall()
        for user in users:
            print(f"  - {user[0]} ({user[1]}) - {user[2]} - 密码: {user[3]} - 状态: {user[4]}")
        
        conn.close()
        
        print(f"\n✓ 数据库迁移成功!")
        print(f"\n默认管理员密码: {default_admin_password}")
        print("请在首次登录后修改密码")
        
        return True
        
    except Exception as e:
        print(f"✗ 数据库迁移失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 尝试回滚
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("数据库迁移工具 - 添加密码字段")
    print("=" * 60)
    
    # 获取数据库路径
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
        print(f"使用命令行参数指定的数据库路径: {db_path}")
    else:
        # 默认路径
        try:
            from qrmes_shared_core.config import config
            if not config.use_webdav:
                data_dir = Path(config.nas_local_base_path)
            else:
                base_dir = Path(__file__).parent.parent
                data_dir = base_dir / "app" / "files"
            
            db_path = data_dir / "users.db"
        except Exception as e:
            print(f"无法从config加载路径: {e}")
            # 使用默认路径
            base_dir = Path(__file__).parent.parent
            db_path = base_dir / "app" / "files" / "users.db"
        
        print(f"使用默认数据库路径: {db_path}")
    
    # 获取默认密码
    if len(sys.argv) > 2:
        default_password = sys.argv[2]
        print(f"使用命令行参数指定的密码")
        confirm = 'y'  # 命令行模式自动确认
    else:
        default_password = input("\n请输入默认管理员密码（默认: admin123）: ").strip() or "admin123"
        print(f"\n将为管理员账户设置密码: {default_password}")
        confirm = input("\n确认执行迁移? (y/N): ").strip().lower()
    
    if confirm == 'y':
        success = migrate_database(db_path, default_password)
        
        if success:
            print("\n✓ 迁移完成!")
            print("\n下一步:")
            print("  1. 重启 mesapp.py 服务")
            print("  2. 使用新密码登录")
            print(f"  3. 默认密码: {default_password}")
        else:
            print("\n✗ 迁移失败，请检查错误信息")
            sys.exit(1)
    else:
        print("\n已取消迁移")
        sys.exit(0)
    
    print("=" * 60)


if __name__ == "__main__":
    main()
