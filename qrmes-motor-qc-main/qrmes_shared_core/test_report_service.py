#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试报告管理服务
解析反电势测试 Word 文档，提取结构化数据
"""

from __future__ import annotations

import os
import re
import sqlite3
import logging
import threading
import time
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# 尝试导入 python-docx
try:
    from docx import Document
    from docx.table import Table
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx 未安装，Word 解析功能不可用。请运行: pip install python-docx")


@dataclass
class TestValue:
    """测试值数据类"""
    name: str
    value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    is_pass: bool
    value_type: str  # 'calibration' 或 'record'


@dataclass
class TestReport:
    """测试报告数据类"""
    serial_number: str
    project_name: str
    test_module: str
    test_result: str  # 'Pass' 或 'Fail'
    test_time: datetime
    file_path: str
    file_name: str
    report_type: str = "BEMF"  # BEMF(反电势) 或 HIL
    description: str = ""
    test_values: List[TestValue] = None
    attachments: Dict[str, str] = None  # {type: filename}
    
    def __post_init__(self):
        if self.test_values is None:
            self.test_values = []
        if self.attachments is None:
            self.attachments = {}


class WordDocParser:
    """Word 文档解析器"""
    
    def __init__(self):
        if not DOCX_AVAILABLE:
            raise RuntimeError("python-docx 未安装")
    
    def parse(self, file_path: Path) -> Optional[TestReport]:
        """解析 Word 文档，提取测试报告数据"""
        try:
            doc = Document(str(file_path))
            
            # 从文件名提取信息
            file_info = self._parse_filename(file_path.name)
            # 从目录路径提取补充信息（例如 反电势_2025_10_09_17_44_26）
            path_info = self._parse_path_context(file_path)
            
            # 从文档内容提取信息
            content_info = self._parse_document_content(doc)
            
            # 合并信息
            report = TestReport(
                serial_number=content_info.get('serial_number') or file_info.get('serial_number', ''),
                project_name=file_path.parent.name,  # 父文件夹名作为项目名
                test_module=content_info.get('test_module', ''),
                test_result=file_info.get('test_result') or content_info.get('test_result', 'Unknown'),
                test_time=file_info.get('test_time') or path_info.get('test_time') or datetime.now(),
                file_path=str(file_path),
                file_name=file_path.name,
                description=content_info.get('description', ''),
                test_values=content_info.get('test_values', []),
                attachments=content_info.get('attachments', {})
            )
            
            return report
            
        except Exception as e:
            logger.error(f"解析 Word 文档失败 {file_path}: {e}")
            return None
    
    def _parse_filename(self, filename: str) -> Dict[str, Any]:
        """
        从文件名解析信息
        常见格式:
        - TZ80013925090008 2025 09 28 16 34 27 Pass.docx
        - TZ80013925090008_2025_09_28_16_34_27_Pass.docx
        """
        info = {}
        
        # 移除扩展名
        name = re.sub(r'\.(docx?|DOCX?)$', '', filename)
        
        # 尝试匹配格式: 序列号 + 日期时间 + 结果（支持空格或下划线）
        pattern = (
            r'^(.+?)[_\s]+(\d{4})[_\s]+(\d{1,2})[_\s]+(\d{1,2})'
            r'[_\s]+(\d{1,2})[_\s]+(\d{1,2})[_\s]+(\d{1,2})[_\s]+(Pass|Fail)$'
        )
        match = re.match(pattern, name, re.IGNORECASE)
        
        if match:
            info['serial_number'] = match.group(1).strip()
            try:
                info['test_time'] = datetime(
                    int(match.group(2)),  # 年
                    int(match.group(3)),  # 月
                    int(match.group(4)),  # 日
                    int(match.group(5)),  # 时
                    int(match.group(6)),  # 分
                    int(match.group(7))   # 秒
                )
            except ValueError:
                pass
            info['test_result'] = match.group(8).capitalize()
        else:
            # 尝试提取文件名前缀作为序列号
            prefix_match = re.match(r'^(.+?)[_\s]+\d{4}[_\s]+\d{1,2}[_\s]+\d{1,2}', name)
            if prefix_match:
                info['serial_number'] = prefix_match.group(1).strip()
            else:
                # 回退：取第一个片段
                parts = [p for p in re.split(r'[_\s]+', name) if p]
                if parts and re.search(r'\d', parts[0]):
                    info['serial_number'] = parts[0]
            
            # 尝试提取日期时间（即使结果字段缺失）
            time_match = re.search(
                r'(\d{4})[_\s]+(\d{1,2})[_\s]+(\d{1,2})[_\s]+'
                r'(\d{1,2})[_\s]+(\d{1,2})[_\s]+(\d{1,2})',
                name
            )
            if time_match:
                try:
                    info['test_time'] = datetime(
                        int(time_match.group(1)),
                        int(time_match.group(2)),
                        int(time_match.group(3)),
                        int(time_match.group(4)),
                        int(time_match.group(5)),
                        int(time_match.group(6))
                    )
                except ValueError:
                    pass
            
            # 检查是否包含 Pass 或 Fail
            result_match = re.search(r'(^|[_\s])(Pass|Fail)($|[_\s])', name, re.IGNORECASE)
            if result_match:
                info['test_result'] = result_match.group(2).capitalize()
        
        return info

    def _parse_path_context(self, file_path: Path) -> Dict[str, Any]:
        """从文件路径中提取补充信息（当前用于提取测试时间）。"""
        info: Dict[str, Any] = {}
        # 从近到远扫描父目录名，优先使用最接近报告文件的时间标签
        candidates = [p.name for p in file_path.parents]
        for name in candidates:
            time_match = re.search(
                r'(\d{4})[_\s]+(\d{1,2})[_\s]+(\d{1,2})[_\s]+'
                r'(\d{1,2})[_\s]+(\d{1,2})[_\s]+(\d{1,2})',
                name
            )
            if not time_match:
                continue
            try:
                info['test_time'] = datetime(
                    int(time_match.group(1)),
                    int(time_match.group(2)),
                    int(time_match.group(3)),
                    int(time_match.group(4)),
                    int(time_match.group(5)),
                    int(time_match.group(6))
                )
                return info
            except ValueError:
                continue
        return info
    
    def _parse_document_content(self, doc: Document) -> Dict[str, Any]:
        """从文档内容解析信息"""
        info = {
            'test_values': [],
            'attachments': {}
        }
        
        # 解析表格
        for table in doc.tables:
            self._parse_table(table, info)
        
        return info
    
    def _parse_table(self, table: Table, info: Dict[str, Any]):
        """解析表格内容"""
        try:
            rows = table.rows
            for i, row in enumerate(rows):
                cells = [cell.text.strip() for cell in row.cells]
                
                if len(cells) < 2:
                    continue
                
                # 匹配常见字段
                key = cells[0]
                value = cells[1] if len(cells) > 1 else ''
                
                if '测试模块' in key:
                    info['test_module'] = value
                elif '说明' in key:
                    info['description'] = value
                elif '测试结果' in key:
                    if '通过' in value:
                        info['test_result'] = 'Pass'
                    elif '失败' in value or '不通过' in value:
                        info['test_result'] = 'Fail'
                    else:
                        info['test_result'] = value
                elif '序列号' in key:
                    info['serial_number'] = value
                elif '记录测试值' in key:
                    serial = self._extract_serial_from_record_row(cells)
                    if serial:
                        info['serial_number'] = serial
                elif '总线记录' in key:
                    info['attachments']['bus_record'] = value
                elif '运行记录' in key:
                    info['attachments']['run_record'] = value
                
                # 仅在“校验测试值”表头行触发解析，避免重复解析记录值区块
                if '校验测试值' in key and '名称' in cells and '值' in cells:
                    # 这可能是测试值表头，解析后续行
                    self._parse_test_values_table(rows, i, info)
                    
        except Exception as e:
            logger.debug(f"解析表格时出错: {e}")
    
    def _parse_test_values_table(self, rows, start_idx: int, info: Dict[str, Any]):
        """解析测试值表格"""
        try:
            # 找到表头行
            header_row = None
            for i in range(start_idx, min(start_idx + 3, len(rows))):
                cells = [cell.text.strip() for cell in rows[i].cells]
                first_col = cells[0] if cells else ''
                if '校验测试值' in first_col and '名称' in cells and '值' in cells:
                    header_row = i
                    break
            
            if header_row is None:
                return
            
            # 获取列索引
            header_cells = [cell.text.strip() for cell in rows[header_row].cells]
            name_idx = header_cells.index('名称') if '名称' in header_cells else -1
            value_idx = header_cells.index('值') if '值' in header_cells else -1
            min_idx = header_cells.index('最小值') if '最小值' in header_cells else -1
            max_idx = header_cells.index('最大值') if '最大值' in header_cells else -1
            
            if name_idx < 0 or value_idx < 0:
                return
            
            # 解析数据行
            for i in range(header_row + 1, len(rows)):
                cells = [cell.text.strip() for cell in rows[i].cells]
                if len(cells) <= max(name_idx, value_idx):
                    continue

                first_col = cells[0] if cells else ''
                # 到达其他区块时结束，只保留“校验测试值”区块的数据
                if any(marker in first_col for marker in ['记录测试值', '总线记录', '运行记录', '测试模块', '测试结果', '说明']):
                    break
                if first_col and '校验测试值' not in first_col:
                    break
                
                name = cells[name_idx] if name_idx < len(cells) else ''
                if not name or name == '名称':
                    continue
                
                value = self._parse_numeric(cells[value_idx]) if value_idx < len(cells) else None
                min_val = self._parse_numeric(cells[min_idx]) if min_idx >= 0 and min_idx < len(cells) else None
                max_val = self._parse_numeric(cells[max_idx]) if max_idx >= 0 and max_idx < len(cells) else None

                # 反电势值必须是可解析数值；无效值直接跳过
                if value is None:
                    continue
                
                # 判断是否合格
                is_pass = True
                if value is not None:
                    if min_val is not None and value < min_val:
                        is_pass = False
                    if max_val is not None and value > max_val:
                        is_pass = False
                
                test_value = TestValue(
                    name=name,
                    value=value,
                    min_value=min_val,
                    max_value=max_val,
                    is_pass=is_pass,
                    value_type='calibration'
                )
                info['test_values'].append(test_value)
                
        except Exception as e:
            logger.debug(f"解析测试值表格时出错: {e}")

    @staticmethod
    def _parse_numeric(raw: str) -> Optional[float]:
        """从文本中提取数值，支持单位（如 11.128V）与逗号小数。"""
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None

        # 优先兼容欧洲小数格式（例如 11,128）
        normalized = text.replace(',', '.')
        match = re.search(r'-?\d+(?:\.\d+)?', normalized)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    @staticmethod
    def _extract_serial_from_record_row(cells: List[str]) -> Optional[str]:
        """
        从“记录测试值”行里提取序列号。
        常见行形态：['记录测试值','序列号SN','序列号SN','Genesis...','Genesis...']
        """
        if not cells:
            return None
        labels = ('序列号', 'SN', 'SERIAL')
        label_idx = None
        for i, text in enumerate(cells):
            text_upper = str(text).upper()
            if any(label in text_upper for label in labels):
                label_idx = i
                break
        if label_idx is None:
            return None

        for i in range(label_idx + 1, len(cells)):
            candidate = str(cells[i]).strip()
            if not candidate:
                continue
            upper = candidate.upper()
            if upper in {'SN', 'SERIAL'}:
                continue
            if '序列号' in candidate:
                continue
            if re.search(r'[A-Za-z0-9]', candidate):
                return candidate
        return None


class TestReportRepository:
    """测试报告数据库仓库"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_database()

    def _connect(self) -> sqlite3.Connection:
        """Create a SQLite connection resilient to concurrent import scans."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn
    
    def _init_database(self):
        """初始化数据库表"""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS test_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial_number TEXT NOT NULL,
                    project_name TEXT,
                    test_module TEXT,
                    test_result TEXT,
                    test_time DATETIME,
                    file_path TEXT UNIQUE,
                    file_name TEXT,
                    report_type TEXT DEFAULT 'BEMF',
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS test_values (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER REFERENCES test_reports(id) ON DELETE CASCADE,
                    value_name TEXT,
                    value REAL,
                    min_value REAL,
                    max_value REAL,
                    is_pass BOOLEAN,
                    value_type TEXT
                );
                
                CREATE TABLE IF NOT EXISTS test_attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER REFERENCES test_reports(id) ON DELETE CASCADE,
                    attachment_type TEXT,
                    file_name TEXT,
                    file_path TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_reports_serial ON test_reports(serial_number);
                CREATE INDEX IF NOT EXISTS idx_reports_project ON test_reports(project_name);
                CREATE INDEX IF NOT EXISTS idx_reports_time ON test_reports(test_time);
            """)
            self._ensure_compat_schema(conn)

    def _ensure_compat_schema(self, conn: sqlite3.Connection):
        """兼容旧库：确保 report_type 字段与索引存在。"""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(test_reports)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'report_type' not in columns:
            cursor.execute("ALTER TABLE test_reports ADD COLUMN report_type TEXT DEFAULT 'BEMF'")
        cursor.execute("UPDATE test_reports SET report_type = 'BEMF' WHERE report_type IS NULL OR TRIM(report_type) = ''")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_type ON test_reports(report_type)")
        conn.commit()
    
    def save_report(self, report: TestReport) -> int:
        """保存测试报告"""
        last_error = None
        for attempt in range(3):
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    report_id = self._upsert_report_header(cursor, report)
                    cursor.execute("DELETE FROM test_values WHERE report_id = ?", (report_id,))
                    cursor.execute("DELETE FROM test_attachments WHERE report_id = ?", (report_id,))

                    for tv in report.test_values:
                        cursor.execute("""
                            INSERT INTO test_values (
                                report_id, value_name, value, min_value, max_value, is_pass, value_type
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            report_id, tv.name, tv.value, tv.min_value, tv.max_value,
                            tv.is_pass, tv.value_type
                        ))

                    for att_type, att_name in report.attachments.items():
                        cursor.execute("""
                            INSERT INTO test_attachments (report_id, attachment_type, file_name)
                            VALUES (?, ?, ?)
                        """, (report_id, att_type, att_name))

                    conn.commit()
                    return report_id
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "database is locked" not in str(exc).lower() or attempt >= 2:
                    raise
                logger.warning(
                    "测试报告数据库繁忙，重试保存 file_path=%s attempt=%s",
                    report.file_path,
                    attempt + 1,
                )
                time.sleep(0.2 * (attempt + 1))

        if last_error is not None:
            raise last_error
        raise RuntimeError("保存测试报告失败：未知错误")

    def _upsert_report_header(self, cursor: sqlite3.Cursor, report: TestReport) -> int:
        cursor.execute("SELECT id FROM test_reports WHERE file_path = ?", (report.file_path,))
        existing = cursor.fetchone()
        if existing:
            report_id = existing[0]
            self._update_report_header(cursor, report_id, report)
            return report_id

        try:
            cursor.execute("""
                INSERT INTO test_reports (
                    serial_number, project_name, test_module, test_result,
                    test_time, file_path, file_name, report_type, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report.serial_number, report.project_name, report.test_module,
                report.test_result, report.test_time, report.file_path,
                report.file_name, report.report_type, report.description
            ))
            return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if "test_reports.file_path" not in str(exc):
                raise
            logger.warning("检测到重复导入竞争，改为更新现有报告: %s", report.file_path)
            cursor.execute("SELECT id FROM test_reports WHERE file_path = ?", (report.file_path,))
            existing = cursor.fetchone()
            if not existing:
                raise
            report_id = existing[0]
            self._update_report_header(cursor, report_id, report)
            return report_id

    @staticmethod
    def _update_report_header(cursor: sqlite3.Cursor, report_id: int, report: TestReport) -> None:
        cursor.execute("""
            UPDATE test_reports SET
                serial_number = ?, project_name = ?, test_module = ?,
                test_result = ?, test_time = ?, file_name = ?,
                report_type = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            report.serial_number, report.project_name, report.test_module,
            report.test_result, report.test_time, report.file_name,
            report.report_type, report.description, report_id
        ))
    
    def get_report_by_id(self, report_id: int) -> Optional[Dict]:
        """根据 ID 获取报告"""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM test_reports WHERE id = ?", (report_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            report = dict(row)
            
            # 获取测试值
            cursor.execute("SELECT * FROM test_values WHERE report_id = ?", (report_id,))
            report['test_values'] = [dict(r) for r in cursor.fetchall()]
            
            # 获取附件
            cursor.execute("SELECT * FROM test_attachments WHERE report_id = ?", (report_id,))
            report['attachments'] = [dict(r) for r in cursor.fetchall()]
            
            return report
    
    def get_reports_by_serial(self, serial_number: str) -> List[Dict]:
        """根据序列号获取报告列表"""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM test_reports 
                WHERE serial_number = ? 
                ORDER BY test_time DESC
            """, (serial_number,))
            
            return [dict(r) for r in cursor.fetchall()]
    
    def list_reports(self, project_name: str = None, test_result: str = None,
                     serial_keyword: str = None,
                     report_type: str = None,
                     date_from: str = None, date_to: str = None,
                     limit: int = 100, offset: int = 0) -> Tuple[List[Dict], int]:
        """列出报告（支持过滤和分页）"""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if project_name:
                conditions.append("project_name = ?")
                params.append(project_name)
            if test_result:
                conditions.append("test_result = ?")
                params.append(test_result)
            if serial_keyword:
                conditions.append("serial_number LIKE ?")
                params.append(f"%{serial_keyword}%")
            if report_type:
                conditions.append("UPPER(report_type) = UPPER(?)")
                params.append(report_type)
            if date_from:
                conditions.append("test_time >= ?")
                params.append(date_from)
            if date_to:
                conditions.append("test_time <= ?")
                params.append(date_to)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # 获取总数
            cursor.execute(f"SELECT COUNT(*) FROM test_reports WHERE {where_clause}", params)
            total = cursor.fetchone()[0]
            
            # 获取分页数据
            cursor.execute(f"""
                SELECT * FROM test_reports 
                WHERE {where_clause}
                ORDER BY test_time DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset])
            
            reports = [dict(r) for r in cursor.fetchall()]
            
            return reports, total
    
    def get_statistics(self, project_name: str = None, report_type: str = None) -> Dict:
        """获取统计信息"""
        with self._connect() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []
            if project_name:
                conditions.append("project_name = ?")
                params.append(project_name)
            if report_type:
                conditions.append("UPPER(report_type) = UPPER(?)")
                params.append(report_type)
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # 总数
            cursor.execute(f"SELECT COUNT(*) FROM test_reports WHERE {where_clause}", params)
            total = cursor.fetchone()[0]
            
            # 通过数
            cursor.execute(f"SELECT COUNT(*) FROM test_reports WHERE {where_clause} AND test_result = 'Pass'", params)
            passed = cursor.fetchone()[0]
            
            # 失败数
            cursor.execute(f"SELECT COUNT(*) FROM test_reports WHERE {where_clause} AND test_result = 'Fail'", params)
            failed = cursor.fetchone()[0]
            
            # 项目列表（跟随过滤条件）
            cursor.execute(
                f"SELECT DISTINCT project_name FROM test_reports WHERE {where_clause} AND project_name IS NOT NULL",
                params
            )
            projects = [r[0] for r in cursor.fetchall()]

            cursor.execute(
                f"SELECT COALESCE(report_type, 'BEMF') AS rt, COUNT(*) FROM test_reports WHERE {where_clause} GROUP BY rt",
                params
            )
            report_types = {str(r[0]).upper(): r[1] for r in cursor.fetchall()}
            
            return {
                'total': total,
                'passed': passed,
                'failed': failed,
                'pass_rate': round(passed / total * 100, 2) if total > 0 else 0,
                'projects': projects,
                'report_types': report_types
            }


class TestReportService:
    """测试报告管理服务"""
    
    def __init__(self, db_path: Path, data_root: Any):
        self.repository = TestReportRepository(db_path)
        self.data_sources = self._normalize_data_sources(data_root)
        self.parser = WordDocParser() if DOCX_AVAILABLE else None
        self._scan_lock = threading.Lock()

    @staticmethod
    def _is_docx_package(file_path: Path) -> bool:
        """判断文件是否为可解析的 docx（ZIP 包）。"""
        try:
            return zipfile.is_zipfile(file_path)
        except OSError:
            return False

    @staticmethod
    def _normalize_report_type(value: str) -> str:
        normalized = (value or "BEMF").strip().upper()
        if "HIL" in normalized:
            return "HIL"
        return "BEMF"

    def _normalize_data_sources(self, data_root: Any) -> List[Tuple[Path, str]]:
        """兼容单目录与多目录配置，返回 [(root_path, report_type), ...]。"""
        sources: List[Tuple[Path, str]] = []
        if isinstance(data_root, (list, tuple)):
            iterable = data_root
        else:
            iterable = [data_root]

        for item in iterable:
            if isinstance(item, dict):
                root_value = item.get('root') or item.get('path')
                if not root_value:
                    continue
                root_path = Path(root_value)
                report_type = self._normalize_report_type(item.get('report_type', 'BEMF'))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                root_path = Path(item[0])
                report_type = self._normalize_report_type(str(item[1]))
            else:
                root_path = Path(item)
                report_type = "BEMF"

            root_key = str(root_path)
            if root_key and all(str(p) != root_key for p, _ in sources):
                sources.append((root_path, report_type))

        return sources
    
    def scan_and_import(self, project_filter: str = None) -> Dict[str, Any]:
        """扫描目录并导入测试报告"""
        if not self.parser:
            return {'success': False, 'error': 'python-docx 未安装'}

        if not self.data_sources:
            return {'success': False, 'error': '未配置测试报告数据目录'}

        if not self._scan_lock.acquire(blocking=False):
            logger.warning("测试报告扫描任务已在执行中，拒绝重复请求")
            return {'success': False, 'error': '扫描任务正在执行，请稍后重试'}
        
        stats = {
            'scanned': 0,
            'imported': 0,
            'failed': 0,
            'skipped_invalid_docx': 0,
            'skipped_invalid_docx_samples': [],
            'sources': [],
            'errors': []
        }

        try:
            for source_root, report_type in self.data_sources:
                stats['sources'].append({'root': str(source_root), 'report_type': report_type})
                if not source_root.exists():
                    stats['errors'].append(f"数据目录不存在: {source_root}")
                    logger.warning(f"跳过不存在的数据目录: {source_root}")
                    continue

                for project_dir in source_root.iterdir():
                    if not project_dir.is_dir():
                        continue

                    if project_filter and project_filter not in project_dir.name:
                        continue

                    logger.info(f"扫描项目: {project_dir.name} [{report_type}]")

                    seen_docx_files: set[str] = set()
                    for pattern in ('*.docx', '*.DOCX'):
                        for docx_file in project_dir.rglob(pattern):
                            file_key = str(docx_file)
                            if file_key in seen_docx_files:
                                continue
                            seen_docx_files.add(file_key)
                            if docx_file.name.startswith('~$'):
                                continue
                            stats['scanned'] += 1

                            if not self._is_docx_package(docx_file):
                                stats['skipped_invalid_docx'] += 1
                                if len(stats['skipped_invalid_docx_samples']) < 20:
                                    stats['skipped_invalid_docx_samples'].append(str(docx_file))
                                continue

                            try:
                                report = self.parser.parse(docx_file)
                                if report:
                                    report.report_type = report_type
                                    self.repository.save_report(report)
                                    stats['imported'] += 1
                                    logger.debug(f"导入成功: {docx_file.name}")
                                else:
                                    stats['failed'] += 1
                                    stats['errors'].append(f"解析失败: {docx_file.name}")
                            except Exception as e:
                                stats['failed'] += 1
                                stats['errors'].append(f"{docx_file.name}: {str(e)}")
                                logger.error(f"导入失败 {docx_file}: {e}")

            logger.info(f"扫描完成: 扫描 {stats['scanned']}, 导入 {stats['imported']}, 失败 {stats['failed']}")

            return {
                'success': True,
                'stats': stats
            }
        finally:
            self._scan_lock.release()
    
    def get_product_complete_info(self, serial_number: str) -> Dict[str, Any]:
        """
        获取产品完整信息（用于生成出厂报告）
        整合：测试报告 + 物料信息 + 工序照片
        """
        info = {
            'serial_number': serial_number,
            'test_reports': [],
            'material_info': None,
            'process_photos': []
        }
        
        # 获取测试报告
        info['test_reports'] = self.repository.get_reports_by_serial(serial_number)
        
        # TODO: 从 MES 系统获取物料信息
        # info['material_info'] = self._get_material_info(serial_number)
        
        # TODO: 从照片管理模块获取工序照片
        # info['process_photos'] = self._get_process_photos(serial_number)
        
        return info
    
    def get_statistics(self, project_name: str = None, report_type: str = None) -> Dict:
        """获取统计信息"""
        return self.repository.get_statistics(project_name, report_type)
    
    def list_reports(self, **kwargs) -> Tuple[List[Dict], int]:
        """列出报告"""
        return self.repository.list_reports(**kwargs)
    
    def get_report(self, report_id: int) -> Optional[Dict]:
        """获取报告详情"""
        return self.repository.get_report_by_id(report_id)


# 用于快速测试
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    # 测试路径
    test_data_root = Path('/volume2/测试中心/3、下线台架测试 Offline test data/1、台架测试数据/3、反电势数据')
    db_path = Path('data/test_reports.db')
    
    if DOCX_AVAILABLE:
        service = TestReportService(db_path, test_data_root)
        result = service.scan_and_import()
        print(f"扫描结果: {result}")
        
        stats = service.get_statistics()
        print(f"统计信息: {stats}")
    else:
        print("请先安装 python-docx: pip install python-docx")
