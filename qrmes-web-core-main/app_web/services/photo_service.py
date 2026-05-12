"""
照片服务 - 优化的查询和分页

提供高性能的照片查询、分页和统计功能
"""

from typing import List, Dict, Optional, Tuple
from pathlib import Path
import sqlite3
import logging
import sys

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.cache_service import CacheService

logger = logging.getLogger(__name__)


class PhotoService:
    """照片服务 - 优化的数据库查询"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.cache = CacheService()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_photos_paginated(
        self,
        inspection_id: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 50,
        cursor_id: Optional[int] = None
    ) -> Tuple[List[Dict], Optional[int]]:
        """
        分页获取照片列表（游标分页，比 OFFSET 更高效）

        Args:
            inspection_id: 质检 ID（可选）
            project_id: 项目 ID（可选）
            limit: 每页数量（默认 50）
            cursor_id: 游标 ID（上一页最后一条记录的 ID）

        Returns:
            (照片列表, 下一页游标 ID)
        """
        limit = min(max(1, limit), 200)  # 限制在 1-200 之间

        # 生成缓存键
        cache_key = f"{inspection_id or 'all'}:{project_id or 'all'}:{limit}:{cursor_id or 'first'}"

        # 尝试从缓存获取
        cached_data = self.cache.get_photo_list(cache_key)
        if cached_data:
            photos = cached_data.get('photos', [])
            next_cursor = cached_data.get('next_cursor')
            logger.debug(f"从缓存获取照片列表: {len(photos)} 条")
            return photos, next_cursor

        conn = self._get_connection()
        cursor = conn.cursor()

        # 只查询需要的字段，避免 SELECT *
        sql = """
            SELECT
                p.id,
                p.photo_id,
                p.inspection_id,
                p.file_name,
                p.uploaded_at
            FROM photos p
        """

        params = []
        where_clauses = []

        # 添加过滤条件
        if inspection_id:
            where_clauses.append("p.inspection_id = ?")
            params.append(inspection_id)

        if project_id:
            # 需要 JOIN inspections 表
            sql = """
                SELECT
                    p.id,
                    p.photo_id,
                    p.inspection_id,
                    p.file_name,
                    p.uploaded_at
                FROM photos p
                INNER JOIN inspections i ON p.inspection_id = i.inspection_id
            """
            where_clauses.append("i.project_id = ?")
            params.append(project_id)

        # 游标分页（比 OFFSET 更高效，特别是大数据量时）
        if cursor_id:
            where_clauses.append("p.id < ?")
            params.append(cursor_id)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        # 按 ID 降序排序，多查一条判断是否有下一页
        sql += " ORDER BY p.id DESC LIMIT ?"
        params.append(limit + 1)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        # 判断是否有下一页
        has_next = len(rows) > limit
        if has_next:
            rows = rows[:limit]

        photos = [dict(row) for row in rows]
        next_cursor = photos[-1]['id'] if photos and has_next else None

        # 设置缓存
        cache_data = {
            'photos': photos,
            'next_cursor': next_cursor
        }
        self.cache.set_photo_list(cache_key, cache_data)
        logger.debug(f"缓存照片列表: {len(photos)} 条")

        return photos, next_cursor

    def get_photo_count(
        self,
        inspection_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> int:
        """
        获取照片总数

        Args:
            inspection_id: 质检 ID（可选）
            project_id: 项目 ID（可选）

        Returns:
            照片总数
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        params = []
        where_clauses = []

        if inspection_id:
            sql = "SELECT COUNT(*) FROM photos WHERE inspection_id = ?"
            params.append(inspection_id)
        elif project_id:
            sql = """
                SELECT COUNT(*)
                FROM photos p
                INNER JOIN inspections i ON p.inspection_id = i.inspection_id
                WHERE i.project_id = ?
            """
            params.append(project_id)
        else:
            sql = "SELECT COUNT(*) FROM photos"

        try:
            cursor.execute(sql, params)
            count = cursor.fetchone()[0]
        finally:
            conn.close()

        return count

    def get_photo_by_id(self, photo_id: str) -> Optional[Dict]:
        """
        根据 photo_id 获取照片详情

        Args:
            photo_id: 照片 ID

        Returns:
            照片信息字典，不存在则返回 None
        """
        # 尝试从缓存获取
        cached_photo = self.cache.get_photo_metadata(photo_id)
        if cached_photo:
            logger.debug(f"从缓存获取照片元数据: {photo_id}")
            return cached_photo

        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
            SELECT
                id, photo_id, inspection_id,
                file_path, file_name, uploaded_at
            FROM photos
            WHERE photo_id = ?
        """

        try:
            cursor.execute(sql, (photo_id,))
            row = cursor.fetchone()
        finally:
            conn.close()

        photo = dict(row) if row else None

        # 设置缓存
        if photo:
            self.cache.set_photo_metadata(photo_id, photo)
            logger.debug(f"缓存照片元数据: {photo_id}")

        return photo

    def get_recent_photos(self, limit: int = 20) -> List[Dict]:
        """
        获取最近上传的照片

        Args:
            limit: 数量限制（默认 20）

        Returns:
            照片列表
        """
        limit = min(max(1, limit), 100)

        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
            SELECT
                id, photo_id, inspection_id,
                file_name, uploaded_at
            FROM photos
            ORDER BY uploaded_at DESC
            LIMIT ?
        """

        try:
            cursor.execute(sql, (limit,))
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [dict(row) for row in rows]

    def get_inspection_photos(self, inspection_id: str) -> List[Dict]:
        """
        获取指定质检的所有照片（用于小数据量场景）

        Args:
            inspection_id: 质检 ID

        Returns:
            照片列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
            SELECT
                id, inspection_id,
                file_name, uploaded_at
            FROM photos
            WHERE inspection_id = ?
            ORDER BY uploaded_at ASC
        """

        try:
            cursor.execute(sql, (inspection_id,))
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [dict(row) for row in rows]
