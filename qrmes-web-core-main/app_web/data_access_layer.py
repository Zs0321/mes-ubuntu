"""
数据访问层接口
提供用户权限管理和工序记录的数据访问接口
"""

import sqlite3
import logging
import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

SQLITE_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_LOCK_RETRY_COUNT = 3
SQLITE_LOCK_RETRY_DELAY_SECONDS = 0.2


class BaseRepository(ABC):
    """基础数据仓库接口"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
    
    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_TIMEOUT_SECONDS)
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # 不开启 foreign_keys：process_photos.captured_by 存的是用户名而非 users.id
        conn.row_factory = sqlite3.Row
        return conn


class UserRepository(BaseRepository):
    """用户数据仓库"""
    
    def create_user(self, synology_username: str, display_name: str = None, role: str = 'user') -> Optional[str]:
        """创建用户"""
        try:
            user_id = str(uuid.uuid4())
            current_time = int(time.time() * 1000)
            
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO users (id, synology_username, display_name, role, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, synology_username, display_name or synology_username, role, current_time, current_time))
                
                conn.commit()
                logger.info(f"创建用户: {synology_username} (ID: {user_id})")
                return user_id
                
        except sqlite3.IntegrityError as e:
            logger.warning(f"用户已存在: {synology_username}")
            return None
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
            return None
    
    def get_user_by_synology_username(self, synology_username: str) -> Optional[Dict[str, Any]]:
        """根据群晖用户名获取用户"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM users WHERE synology_username = ?",
                    (synology_username,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"查询用户失败: {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """根据用户ID获取用户"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"查询用户失败: {e}")
            return None
    
    def update_user_role(self, user_id: str, role: str) -> bool:
        """更新用户角色"""
        try:
            if role not in ['admin', 'user']:
                logger.error(f"无效的用户角色: {role}")
                return False
            
            current_time = int(time.time() * 1000)
            
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    UPDATE users SET role = ?, updated_at = ?
                    WHERE id = ?
                """, (role, current_time, user_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新用户角色: {user_id} -> {role}")
                    return True
                else:
                    logger.warning(f"用户不存在: {user_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"更新用户角色失败: {e}")
            return False
    
    def update_last_login(self, user_id: str) -> bool:
        """更新最后登录时间"""
        try:
            current_time = int(time.time() * 1000)
            
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    UPDATE users SET last_login_at = ?, updated_at = ?
                    WHERE id = ?
                """, (current_time, current_time, user_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    return True
                else:
                    return False
                    
        except Exception as e:
            logger.error(f"更新最后登录时间失败: {e}")
            return False
    
    def get_all_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有用户"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM users 
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"查询所有用户失败: {e}")
            return []
    
    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除用户: {user_id}")
                    return True
                else:
                    logger.warning(f"用户不存在: {user_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"删除用户失败: {e}")
            return False


class PermissionLogRepository(BaseRepository):
    """权限日志数据仓库"""
    
    def log_permission_check(self, user_id: str, action: str, resource: str, 
                           result: str, ip_address: str = None, user_agent: str = None) -> bool:
        """记录权限检查日志"""
        try:
            if result not in ['allowed', 'denied']:
                logger.error(f"无效的权限检查结果: {result}")
                return False
            
            current_time = int(time.time() * 1000)
            
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO permission_logs 
                    (user_id, action, resource, result, ip_address, user_agent, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, action, resource, result, ip_address, user_agent, current_time))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"记录权限日志失败: {e}")
            return False
    
    def get_permission_logs(self, user_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取权限日志"""
        try:
            with self.get_connection() as conn:
                if user_id:
                    cursor = conn.execute("""
                        SELECT pl.*, u.synology_username, u.display_name
                        FROM permission_logs pl
                        LEFT JOIN users u ON pl.user_id = u.id
                        WHERE pl.user_id = ?
                        ORDER BY pl.created_at DESC
                        LIMIT ?
                    """, (user_id, limit))
                else:
                    cursor = conn.execute("""
                        SELECT pl.*, u.synology_username, u.display_name
                        FROM permission_logs pl
                        LEFT JOIN users u ON pl.user_id = u.id
                        ORDER BY pl.created_at DESC
                        LIMIT ?
                    """, (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"查询权限日志失败: {e}")
            return []
    
    def get_denied_attempts(self, hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
        """获取被拒绝的权限尝试"""
        try:
            time_threshold = int((time.time() - hours * 3600) * 1000)
            
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT pl.*, u.synology_username, u.display_name
                    FROM permission_logs pl
                    LEFT JOIN users u ON pl.user_id = u.id
                    WHERE pl.result = 'denied' AND pl.created_at > ?
                    ORDER BY pl.created_at DESC
                    LIMIT ?
                """, (time_threshold, limit))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"查询被拒绝的权限尝试失败: {e}")
            return []


class ProcessPhotoRepository(BaseRepository):
    """工序照片数据仓库"""

    @staticmethod
    def _normalize_file_path(file_path: str) -> str:
        return str(file_path or "").replace("\\", "/").strip()

    @staticmethod
    def _load_metadata(metadata_text: Optional[str]) -> Dict[str, Any]:
        if not metadata_text:
            return {}
        try:
            return json.loads(metadata_text)
        except Exception:
            return {}

    @staticmethod
    def _merge_metadata(existing_text: Optional[str], incoming: Optional[Dict[str, Any]]) -> str:
        merged = ProcessPhotoRepository._load_metadata(existing_text)
        merged.update(incoming or {})
        return json.dumps(merged, ensure_ascii=False)

    def _find_existing_photo(self, conn: sqlite3.Connection, file_path: str) -> Optional[sqlite3.Row]:
        normalized_path = self._normalize_file_path(file_path)
        cursor = conn.execute(
            """
                SELECT id, metadata
                FROM process_photos
                WHERE file_path = ?
                   OR REPLACE(file_path, '\\', '/') = ?
                ORDER BY id DESC
                LIMIT 1
            """,
            (file_path, normalized_path),
        )
        return cursor.fetchone()
    
    def save_photo_metadata(self, product_serial: str, process_step: str, file_path: str, 
                          file_name: str, file_size: int, captured_by: str, 
                          metadata: Dict[str, Any] = None) -> Optional[int]:
        """保存照片元数据"""
        current_time = int(time.time() * 1000)

        for attempt in range(SQLITE_LOCK_RETRY_COUNT):
            try:
                with self.get_connection() as conn:
                    existing = self._find_existing_photo(conn, file_path)
                    metadata_json = self._merge_metadata(
                        existing["metadata"] if existing else None,
                        metadata,
                    )

                    if existing:
                        photo_id = int(existing["id"])
                        conn.execute(
                            """
                                UPDATE process_photos
                                SET product_serial = ?, process_step = ?, file_path = ?, file_name = ?,
                                    file_size = ?, captured_by = ?, captured_at = ?, metadata = ?
                                WHERE id = ?
                            """,
                            (
                                product_serial,
                                process_step,
                                file_path,
                                file_name,
                                file_size,
                                captured_by,
                                current_time,
                                metadata_json,
                                photo_id,
                            ),
                        )
                        action = "更新"
                    else:
                        cursor = conn.execute(
                            """
                                INSERT INTO process_photos
                                (product_serial, process_step, file_path, file_name, file_size,
                                 captured_by, captured_at, metadata)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                product_serial,
                                process_step,
                                file_path,
                                file_name,
                                file_size,
                                captured_by,
                                current_time,
                                metadata_json,
                            ),
                        )
                        photo_id = int(cursor.lastrowid)
                        action = "保存"

                    conn.commit()
                    logger.info(f"{action}照片元数据: {file_name} (ID: {photo_id})")
                    return photo_id
            except sqlite3.OperationalError as e:
                if "database is locked" not in str(e).lower() or attempt >= SQLITE_LOCK_RETRY_COUNT - 1:
                    logger.error(f"保存照片元数据失败: {e}")
                    return None
                logger.warning(
                    "保存照片元数据遇到数据库锁，准备重试 %s/%s: %s",
                    attempt + 1,
                    SQLITE_LOCK_RETRY_COUNT,
                    e,
                )
                time.sleep(SQLITE_LOCK_RETRY_DELAY_SECONDS * (attempt + 1))
            except Exception as e:
                logger.error(f"保存照片元数据失败: {e}")
                return None

        return None
    
    def get_photos_by_product(self, product_serial: str) -> List[Dict[str, Any]]:
        """获取产品的所有工序照片"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT pp.*, u.synology_username, u.display_name
                    FROM process_photos pp
                    LEFT JOIN users u ON pp.captured_by = u.id
                    WHERE pp.product_serial = ?
                    ORDER BY pp.captured_at ASC
                """, (product_serial,))
                
                photos = []
                for row in cursor.fetchall():
                    photo = dict(row)
                    # 解析metadata JSON
                    if photo.get('metadata'):
                        try:
                            photo['metadata'] = json.loads(photo['metadata'])
                        except:
                            photo['metadata'] = {}
                    photos.append(photo)
                
                return photos
        except Exception as e:
            logger.error(f"查询产品照片失败: {e}")
            return []
    
    def get_photos_by_process_step(self, process_step: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取指定工序的所有照片"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT pp.*, u.synology_username, u.display_name
                    FROM process_photos pp
                    LEFT JOIN users u ON pp.captured_by = u.id
                    WHERE pp.process_step = ?
                    ORDER BY pp.captured_at DESC
                    LIMIT ?
                """, (process_step, limit))
                
                photos = []
                for row in cursor.fetchall():
                    photo = dict(row)
                    if photo.get('metadata'):
                        try:
                            photo['metadata'] = json.loads(photo['metadata'])
                        except:
                            photo['metadata'] = {}
                    photos.append(photo)
                
                return photos
        except Exception as e:
            logger.error(f"查询工序照片失败: {e}")
            return []
    
    def update_upload_status(self, photo_id: int, uploaded: bool = True) -> bool:
        """更新照片上传状态"""
        try:
            upload_time = int(time.time() * 1000) if uploaded else None
            
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    UPDATE process_photos SET uploaded_at = ?
                    WHERE id = ?
                """, (upload_time, photo_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    return True
                else:
                    return False
                    
        except Exception as e:
            logger.error(f"更新照片上传状态失败: {e}")
            return False
    
    def get_photo_by_id(self, photo_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取照片信息"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT pp.*, u.synology_username, u.display_name
                    FROM process_photos pp
                    LEFT JOIN users u ON pp.captured_by = u.id
                    WHERE pp.id = ?
                """, (photo_id,))
                
                row = cursor.fetchone()
                if row:
                    photo = dict(row)
                    # 解析metadata JSON
                    if photo.get('metadata'):
                        try:
                            photo['metadata'] = json.loads(photo['metadata'])
                        except:
                            photo['metadata'] = {}
                    return photo
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"查询照片失败: {e}")
            return None
    
    def update_photo_metadata(self, photo_id: int, metadata: Dict[str, Any]) -> bool:
        """更新照片元数据"""
        try:
            metadata_json = json.dumps(metadata, ensure_ascii=False)
            current_time = int(time.time() * 1000)
            
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    UPDATE process_photos SET metadata = ?, uploaded_at = ?
                    WHERE id = ?
                """, (metadata_json, current_time, photo_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新照片元数据: {photo_id}")
                    return True
                else:
                    logger.warning(f"照片记录不存在: {photo_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"更新照片元数据失败: {e}")
            return False
    
    def get_photos_with_filters(self, product_serial: str = None, process_step: str = None, 
                              captured_by: str = None, date_from: int = None, 
                              date_to: int = None, limit: int = 100) -> List[Dict[str, Any]]:
        """根据多个条件筛选照片"""
        try:
            conditions = []
            params = []
            
            if product_serial:
                conditions.append("pp.product_serial = ?")
                params.append(product_serial)
            
            if process_step:
                conditions.append("pp.process_step = ?")
                params.append(process_step)
            
            if captured_by:
                conditions.append("pp.captured_by = ?")
                params.append(captured_by)
            
            if date_from:
                conditions.append("pp.captured_at >= ?")
                params.append(date_from)
            
            if date_to:
                conditions.append("pp.captured_at <= ?")
                params.append(date_to)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            with self.get_connection() as conn:
                cursor = conn.execute(f"""
                    SELECT pp.*, u.synology_username, u.display_name
                    FROM process_photos pp
                    LEFT JOIN users u ON pp.captured_by = u.id
                    WHERE {where_clause}
                    ORDER BY pp.captured_at DESC
                    LIMIT ?
                """, params)
                
                photos = []
                for row in cursor.fetchall():
                    photo = dict(row)
                    if photo.get('metadata'):
                        try:
                            photo['metadata'] = json.loads(photo['metadata'])
                        except:
                            photo['metadata'] = {}
                    photos.append(photo)
                
                return photos
                
        except Exception as e:
            logger.error(f"筛选照片失败: {e}")
            return []
    
    def get_photo_statistics(self) -> Dict[str, Any]:
        """获取照片统计信息"""
        try:
            with self.get_connection() as conn:
                # 总照片数
                cursor = conn.execute("SELECT COUNT(*) as total FROM process_photos")
                total_photos = cursor.fetchone()['total']
                
                # 已上传照片数
                cursor = conn.execute("SELECT COUNT(*) as uploaded FROM process_photos WHERE uploaded_at IS NOT NULL")
                uploaded_photos = cursor.fetchone()['uploaded']
                
                # 按工序统计
                cursor = conn.execute("""
                    SELECT process_step, COUNT(*) as count 
                    FROM process_photos 
                    GROUP BY process_step 
                    ORDER BY count DESC
                """)
                by_process = [dict(row) for row in cursor.fetchall()]
                
                # 按产品统计
                cursor = conn.execute("""
                    SELECT product_serial, COUNT(*) as count 
                    FROM process_photos 
                    GROUP BY product_serial 
                    ORDER BY count DESC 
                    LIMIT 10
                """)
                by_product = [dict(row) for row in cursor.fetchall()]
                
                # 按日期统计（最近7天）
                seven_days_ago = int((time.time() - 7 * 24 * 3600) * 1000)
                cursor = conn.execute("""
                    SELECT DATE(captured_at/1000, 'unixepoch') as date, COUNT(*) as count
                    FROM process_photos 
                    WHERE captured_at >= ?
                    GROUP BY DATE(captured_at/1000, 'unixepoch')
                    ORDER BY date DESC
                """, (seven_days_ago,))
                by_date = [dict(row) for row in cursor.fetchall()]
                
                return {
                    'totalPhotos': total_photos,
                    'uploadedPhotos': uploaded_photos,
                    'pendingPhotos': total_photos - uploaded_photos,
                    'byProcess': by_process,
                    'byProduct': by_product,
                    'byDate': by_date
                }
                
        except Exception as e:
            logger.error(f"获取照片统计失败: {e}")
            return {}
    
    def delete_photo(self, photo_id: int) -> bool:
        """删除照片记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("DELETE FROM process_photos WHERE id = ?", (photo_id,))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除照片记录: {photo_id}")
                    return True
                else:
                    logger.warning(f"照片记录不存在: {photo_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"删除照片记录失败: {e}")
            return False


class ProcessConfigurationRepository(BaseRepository):
    """工序配置数据仓库"""
    
    def create_process_config(self, name: str, description: str = None, order_index: int = 0,
                            required: bool = True, photo_required: bool = True,
                            estimated_duration: int = 300) -> Optional[str]:
        """创建工序配置"""
        try:
            config_id = str(uuid.uuid4())
            current_time = int(time.time() * 1000)
            
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO process_configurations 
                    (id, name, description, order_index, required, photo_required, 
                     estimated_duration, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (config_id, name, description, order_index, 
                      1 if required else 0, 1 if photo_required else 0,
                      estimated_duration, current_time, current_time))
                
                conn.commit()
                logger.info(f"创建工序配置: {name} (ID: {config_id})")
                return config_id
                
        except Exception as e:
            logger.error(f"创建工序配置失败: {e}")
            return None
    
    def get_all_process_configs(self) -> List[Dict[str, Any]]:
        """获取所有工序配置"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM process_configurations 
                    ORDER BY order_index ASC, name ASC
                """)
                
                configs = []
                for row in cursor.fetchall():
                    config = dict(row)
                    # 转换布尔值
                    config['required'] = bool(config['required'])
                    config['photo_required'] = bool(config['photo_required'])
                    configs.append(config)
                
                return configs
        except Exception as e:
            logger.error(f"查询工序配置失败: {e}")
            return []
    
    def update_process_config(self, config_id: str, updates: Dict[str, Any]) -> bool:
        """更新工序配置"""
        try:
            current_time = int(time.time() * 1000)
            updates['updated_at'] = current_time
            
            # 转换布尔值
            if 'required' in updates:
                updates['required'] = 1 if updates['required'] else 0
            if 'photo_required' in updates:
                updates['photo_required'] = 1 if updates['photo_required'] else 0
            
            # 构建更新语句
            set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [config_id]
            
            with self.get_connection() as conn:
                cursor = conn.execute(f"""
                    UPDATE process_configurations SET {set_clause}
                    WHERE id = ?
                """, values)
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新工序配置: {config_id}")
                    return True
                else:
                    logger.warning(f"工序配置不存在: {config_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"更新工序配置失败: {e}")
            return False
    
    def delete_process_config(self, config_id: str) -> bool:
        """删除工序配置"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("DELETE FROM process_configurations WHERE id = ?", (config_id,))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除工序配置: {config_id}")
                    return True
                else:
                    logger.warning(f"工序配置不存在: {config_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"删除工序配置失败: {e}")
            return False


class DataAccessManager:
    """数据访问管理器 - 统一的数据访问入口"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.user_repo = UserRepository(db_path)
        self.permission_log_repo = PermissionLogRepository(db_path)
        self.process_photo_repo = ProcessPhotoRepository(db_path)
        self.process_config_repo = ProcessConfigurationRepository(db_path)
    
    def initialize_database(self) -> bool:
        """初始化数据库"""
        from database_schema import DatabaseSchema
        return DatabaseSchema.initialize_all_tables(self.db_path)
    
    def create_default_admin(self, admin_username: str = "admin") -> bool:
        """创建默认管理员用户"""
        from database_schema import DatabaseSchema
        return DatabaseSchema.create_default_admin_user(self.db_path, admin_username)
