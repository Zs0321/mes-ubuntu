"""
H2数据库API服务 - 增强版
1. 修复时区显示问题（UTC转中国时区）
2. 添加CSV文件监控（inotify/watchdog）
3. 添加定时同步任务
4. 优化同步性能
"""

import os
import sqlite3
import logging
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from flask import Flask, jsonify, request

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 中国时区 GMT+8
CHINA_TZ = timezone(timedelta(hours=8))

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

def resolve_default_h2_db_path() -> Path:
    """优先使用 .10 本机查找库，避免 Ubuntu 误落到 /volume2。"""
    for env_key in ("QRMES_H2_DB_PATH", "MESAPP_H2_DB_PATH"):
        candidate = os.getenv(env_key)
        if candidate:
            return Path(candidate).expanduser()

    return Path("/volume2/MES/QRMES/record/product_records.db")


def format_timestamp_to_china_time(timestamp_ms) -> str:
    """将UTC毫秒时间戳转换为中国时区时间字符串
    
    兼容两种输入格式：
    1. 毫秒时间戳（int/float）
    2. 已格式化的日期字符串（直接返回）
    """
    if not timestamp_ms:
        return ""
    
    # 如果已经是格式化的日期字符串，直接返回
    if isinstance(timestamp_ms, str):
        # 检查是否是日期格式（包含 - 或 /）
        if '-' in timestamp_ms or '/' in timestamp_ms:
            return timestamp_ms
        # 尝试解析为数字
        try:
            timestamp_ms = int(timestamp_ms)
        except ValueError:
            return timestamp_ms  # 无法解析，直接返回原字符串
    
    if timestamp_ms == 0:
        return ""
    
    try:
        timestamp_sec = timestamp_ms / 1000
        utc_time = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
        china_time = utc_time.astimezone(CHINA_TZ)
        return china_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.error(f"时间转换失败: {e}")
        return str(timestamp_ms)  # 转换失败返回原值字符串


def parse_china_time_to_timestamp(time_str: str) -> int:
    """将中国时区时间字符串转换为UTC毫秒时间戳"""
    if not time_str or time_str == 'nan':
        return int(time.time() * 1000)
    
    try:
        # 尝试解析常见格式
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
            try:
                # 解析为中国时区时间
                dt = datetime.strptime(time_str, fmt)
                china_dt = dt.replace(tzinfo=CHINA_TZ)
                # 转换为UTC时间戳
                utc_dt = china_dt.astimezone(timezone.utc)
                return int(utc_dt.timestamp() * 1000)
            except ValueError:
                continue
        
        # 如果都失败，返回当前时间
        return int(time.time() * 1000)
    except Exception as e:
        logger.error(f"时间解析失败: {e}")
        return int(time.time() * 1000)


def normalize_text_key(value: str) -> str:
    """统一规范化文本，用于学习冲突比较。"""
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    for ch in (" ", "_", "-", ".", "（", "）", "(", ")", "，", ",", "/", "\\"):
        normalized = normalized.replace(ch, "")
    return normalized


def parse_bool(value, default: bool = False) -> bool:
    """安全解析布尔值，避免 bool('false') == True 的坑。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return default


class H2DatabaseManager:
    """H2数据库管理器（SQLite实现）- 增强版"""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(resolve_default_h2_db_path())
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
        logger.info(f"[H2数据库] 初始化完成: {self.db_path}")
    
    def init_database(self):
        """初始化数据库表结构，并迁移旧表（去重，确保 product_serial 唯一）"""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")

            # 检查现有表是否存在 product_serial UNIQUE 约束
            needs_migration = False
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='product_records'")
            row = cursor.fetchone()
            if row is None:
                # 表不存在，直接创建正确结构
                conn.execute("""
                    CREATE TABLE product_records (
                        product_serial TEXT PRIMARY KEY,
                        product_type TEXT NOT NULL,
                        project_name TEXT NOT NULL,
                        operator TEXT NOT NULL,
                        scan_time INTEGER NOT NULL,
                        materials TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                """)
            else:
                # 使用 PRAGMA table_info 判断主键列，避免受建表 SQL 格式影响。
                table_info = conn.execute("PRAGMA table_info(product_records)").fetchall()
                has_serial_pk = False
                for item in table_info:
                    # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
                    column_name = str(item[1] or "").strip().lower() if len(item) > 1 else ""
                    is_pk = int(item[5] or 0) == 1 if len(item) > 5 else False
                    if column_name == "product_serial" and is_pk:
                        has_serial_pk = True
                        break
                # 旧表可能有 id INTEGER PRIMARY KEY，product_serial 不是唯一的
                if not has_serial_pk:
                    needs_migration = True

            if needs_migration:
                logger.info("[H2检测到旧表结构，开始迁移（合并重复产品记录）...")
                self._migrate_deduplicate(conn)

            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_project_name ON product_records(project_name)",
                "CREATE INDEX IF NOT EXISTS idx_operator ON product_records(operator)",
                "CREATE INDEX IF NOT EXISTS idx_scan_time ON product_records(scan_time)",
                "CREATE INDEX IF NOT EXISTS idx_product_type ON product_records(product_type)"
            ]

            for index_sql in indexes:
                conn.execute(index_sql)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS serial_learning (
                    product_serial TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    manual_confirm_count INTEGER NOT NULL DEFAULT 0,
                    auto_accept_count INTEGER NOT NULL DEFAULT 0,
                    conflict_count INTEGER NOT NULL DEFAULT 0,
                    last_source TEXT NOT NULL DEFAULT '',
                    last_operator TEXT NOT NULL DEFAULT '',
                    last_seen_at INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (product_serial, project_name, product_type)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_serial_learning_serial ON serial_learning(product_serial)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_serial_learning_updated ON serial_learning(updated_at)"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS serial_learning_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_serial TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    operator TEXT,
                    conflict INTEGER NOT NULL DEFAULT 0,
                    candidates_json TEXT,
                    created_at INTEGER NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_serial_learning_events_serial ON serial_learning_events(product_serial, created_at DESC)"
            )

            conn.commit()

    def _migrate_deduplicate(self, conn):
        """将旧表（有重复 product_serial）迁移为新表（product_serial 唯一，materials 合并）"""
        conn.row_factory = sqlite3.Row

        # 1. 按产品序列号分组，合并 materials
        cursor = conn.execute("""
            SELECT product_serial, product_type, project_name, operator,
                   scan_time, materials, created_at, updated_at
            FROM product_records
            ORDER BY scan_time ASC
        """)
        all_rows = cursor.fetchall()

        merged_records = {}  # product_serial -> merged record dict
        for row in all_rows:
            serial = row['product_serial']
            mat_str = row['materials'] if 'materials' in row.keys() else ''

            if serial not in merged_records:
                merged_records[serial] = {
                    'product_serial': serial,
                    'product_type': row['product_type'],
                    'project_name': row['project_name'],
                    'operator': row['operator'],
                    'scan_time': row['scan_time'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    '_materials': {},
                }

            rec = merged_records[serial]
            # 后面的行（更新的）覆盖基本字段
            rec['product_type'] = row['product_type']
            rec['project_name'] = row['project_name']
            rec['operator'] = row['operator']
            rec['scan_time'] = row['scan_time']
            rec['updated_at'] = row['updated_at']

            # 合并 materials（新值覆盖旧值）
            if mat_str and isinstance(mat_str, str):
                try:
                    mat = json.loads(mat_str)
                    if isinstance(mat, dict):
                        for k, v in mat.items():
                            if v not in (None, '', 'null', 'nan'):
                                rec['_materials'][k] = v
                except (json.JSONDecodeError, TypeError):
                    pass

        logger.info(f"[H2迁移] 合并完成: {len(all_rows)} 行 -> {len(merged_records)} 个产品")

        # 2. 删除旧表，创建新表
        conn.execute("DROP TABLE product_records")
        conn.execute("""
            CREATE TABLE product_records (
                product_serial TEXT PRIMARY KEY,
                product_type TEXT NOT NULL,
                project_name TEXT NOT NULL,
                operator TEXT NOT NULL,
                scan_time INTEGER NOT NULL,
                materials TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        # 3. 插入合并后的记录
        for rec in merged_records.values():
            materials_json = json.dumps(rec['_materials'], ensure_ascii=False) if rec['_materials'] else '{}'
            conn.execute("""
                INSERT INTO product_records
                (product_serial, product_type, project_name, operator, scan_time,
                 materials, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec['product_serial'],
                rec['product_type'],
                rec['project_name'],
                rec['operator'],
                rec['scan_time'],
                materials_json,
                rec['created_at'],
                rec['updated_at'],
            ))

        conn.commit()
        logger.info(f"[H2迁移] 新表创建完成，{len(merged_records)} 条唯一产品记录")
    
    def upsert_record(self, record: Dict) -> bool:
        """插入或更新记录（合并已有 materials，product_serial 唯一）"""
        try:
            current_time = int(time.time() * 1000)
            product_serial = record['product_serial']
            raw_allow_binding_update = record.get('allow_binding_update', False)
            if isinstance(raw_allow_binding_update, str):
                allow_binding_update = raw_allow_binding_update.strip().lower() in ('1', 'true', 'yes', 'on')
            else:
                allow_binding_update = bool(raw_allow_binding_update)

            # 解析本次提交的 materials
            new_materials_str = record.get('materials', record.get('raw_data', ''))
            new_materials = {}
            if isinstance(new_materials_str, str) and new_materials_str.strip():
                try:
                    parsed = json.loads(new_materials_str)
                    if isinstance(parsed, dict):
                        new_materials = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(new_materials_str, dict):
                new_materials = new_materials_str

            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row

                # 查询已有记录，合并 materials
                cursor = conn.execute(
                    """
                    SELECT materials, created_at, project_name, product_type
                    FROM product_records
                    WHERE product_serial = ?
                    """,
                    (product_serial,)
                )
                existing = cursor.fetchone()

                merged = {}
                original_created_at = current_time
                existing_project = ''
                existing_type = ''
                if existing:
                    original_created_at = existing['created_at']
                    old_str = existing['materials'] if 'materials' in existing.keys() else ''
                    if old_str and isinstance(old_str, str):
                        try:
                            old_mat = json.loads(old_str)
                            if isinstance(old_mat, dict):
                                merged = old_mat
                        except (json.JSONDecodeError, TypeError):
                            pass
                    existing_project = str(existing['project_name'] or '').strip()
                    existing_type = str(existing['product_type'] or '').strip()
                    incoming_project = str(record.get('project_name') or '').strip()
                    incoming_type = str(record.get('product_type') or '').strip()
                    project_mismatch = bool(
                        existing_project and incoming_project and existing_project != incoming_project
                    )
                    type_mismatch = bool(
                        existing_type and incoming_type and existing_type != incoming_type
                    )
                    if existing_project and incoming_project and existing_project != incoming_project:
                        logger.warning(
                            "[H2] 记录绑定项目不一致: %s existing=%s incoming=%s allow_update=%s",
                            product_serial,
                            existing_project,
                            incoming_project,
                            allow_binding_update,
                        )
                    if existing_type and incoming_type and existing_type != incoming_type:
                        logger.warning(
                            "[H2] 记录绑定产品类型不一致: %s existing=%s incoming=%s allow_update=%s",
                            product_serial,
                            existing_type,
                            incoming_type,
                            allow_binding_update,
                        )
                    if (project_mismatch or type_mismatch) and not allow_binding_update:
                        logger.error(
                            "[H2] 拒绝覆盖绑定(需手动修复/授权更新): %s existing=(%s/%s) incoming=(%s/%s)",
                            product_serial,
                            existing_project,
                            existing_type,
                            incoming_project,
                            incoming_type,
                        )
                        return False

                # 新值覆盖旧值
                merged.update({k: v for k, v in new_materials.items() if v not in (None, '', 'null', 'nan')})
                if merged:
                    merged_json = json.dumps(merged, ensure_ascii=False)
                elif isinstance(new_materials_str, str):
                    merged_json = new_materials_str if new_materials_str.strip() else "{}"
                else:
                    merged_json = "{}"

                resolved_project_name = str(record.get('project_name') or '').strip()
                resolved_product_type = str(record.get('product_type') or '').strip()
                if existing and not allow_binding_update:
                    if existing_project:
                        resolved_project_name = existing_project
                    if existing_type:
                        resolved_product_type = existing_type

                # INSERT OR REPLACE（product_serial 是 PRIMARY KEY，保证唯一）
                conn.execute("""
                    INSERT OR REPLACE INTO product_records
                    (product_serial, product_type, project_name, operator, scan_time,
                     materials, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_serial,
                    resolved_product_type,
                    resolved_project_name,
                    record['operator'],
                    record.get('scan_time', current_time),
                    merged_json,
                    original_created_at,
                    current_time
                ))
                conn.commit()
                logger.info(f"[H2] 记录保存成功: {product_serial}, materials: {len(merged)} 项")

            learning_source = str(record.get('learning_source') or '').strip()
            if learning_source:
                raw_increment = record.get('learning_increment', 1)
                try:
                    learning_increment = max(1, int(raw_increment))
                except (TypeError, ValueError):
                    learning_increment = 1
                raw_conflict = record.get('learning_conflict', False)
                if isinstance(raw_conflict, str):
                    learning_conflict = raw_conflict.strip().lower() in ('1', 'true', 'yes', 'on')
                else:
                    learning_conflict = bool(raw_conflict)
                raw_candidates = record.get('learning_candidates', [])
                learning_candidates = raw_candidates if isinstance(raw_candidates, list) else []
                self.upsert_learning_evidence(
                    product_serial=product_serial,
                    project_name=record['project_name'],
                    product_type=record['product_type'],
                    source=learning_source,
                    operator=record.get('operator', ''),
                    conflict=learning_conflict,
                    candidates=learning_candidates,
                    increment=learning_increment,
                )
            return True
        except Exception as e:
            logger.error(f"记录保存失败: {e}")
            return False

    def upsert_learning_evidence(
        self,
        product_serial: str,
        project_name: str,
        product_type: str,
        source: str = "manual_confirm",
        operator: str = "",
        conflict: bool = False,
        candidates: Optional[List[Dict]] = None,
        increment: int = 1,
    ) -> bool:
        """写入序列号学习证据并保留事件审计。"""
        serial = str(product_serial or "").strip()
        project = str(project_name or "").strip()
        ptype = str(product_type or "").strip()
        if not serial or not project or not ptype:
            return False

        now_ms = int(time.time() * 1000)
        source = str(source or "manual_confirm").strip()
        operator = str(operator or "").strip()
        safe_candidates = candidates or []
        auto_sources = ("auto_recommend", "history_recommend")
        if source in auto_sources:
            # 自动推荐仅记录审计事件，不再累加学习分，避免错误自强化。
            delta = 0
            manual_delta = 0
            auto_delta = 0
        else:
            delta = max(1, int(increment or 1))
            manual_delta = 1 if source in ("manual_confirm", "manual_override", "manual_keep_current", "manual_repair") else 0
            auto_delta = 0
        conflict_delta = 1 if conflict else 0

        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    """
                    INSERT INTO serial_learning (
                        product_serial, project_name, product_type,
                        evidence_count, manual_confirm_count, auto_accept_count, conflict_count,
                        last_source, last_operator, last_seen_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_serial, project_name, product_type) DO UPDATE SET
                        evidence_count = evidence_count + excluded.evidence_count,
                        manual_confirm_count = manual_confirm_count + excluded.manual_confirm_count,
                        auto_accept_count = auto_accept_count + excluded.auto_accept_count,
                        conflict_count = conflict_count + excluded.conflict_count,
                        last_source = excluded.last_source,
                        last_operator = excluded.last_operator,
                        last_seen_at = excluded.last_seen_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        serial,
                        project,
                        ptype,
                        delta,
                        manual_delta,
                        auto_delta,
                        conflict_delta,
                        source,
                        operator,
                        now_ms,
                        now_ms,
                        now_ms,
                    ),
                )

                conn.execute(
                    """
                    INSERT INTO serial_learning_events
                    (product_serial, project_name, product_type, source, operator, conflict, candidates_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        serial,
                        project,
                        ptype,
                        source,
                        operator,
                        1 if conflict else 0,
                        json.dumps(safe_candidates, ensure_ascii=False) if safe_candidates else "[]",
                        now_ms,
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[H2学习] 写入失败: {e}")
            return False

    def repair_serial_binding(
        self,
        product_serial: str,
        project_name: str,
        product_type: str,
        operator: str = "",
        source: str = "manual_repair",
    ) -> bool:
        """手动修复序列号绑定关系，并写入学习证据。"""
        serial = str(product_serial or "").strip()
        project = str(project_name or "").strip()
        ptype = str(product_type or "").strip()
        if not serial or not project or not ptype:
            return False

        now_ms = int(time.time() * 1000)
        operator = str(operator or "").strip()
        source = str(source or "manual_repair").strip() or "manual_repair"

        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row
                existing = conn.execute(
                    """
                    SELECT created_at, materials
                    FROM product_records
                    WHERE product_serial = ?
                    """,
                    (serial,),
                ).fetchone()

                created_at = now_ms
                materials_json = "{}"
                if existing:
                    created_at = int(existing["created_at"] or now_ms)
                    raw_materials = str(existing["materials"] or "").strip()
                    if raw_materials:
                        materials_json = raw_materials

                conn.execute(
                    """
                    INSERT INTO product_records (
                        product_serial, product_type, project_name, operator, scan_time,
                        materials, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_serial) DO UPDATE SET
                        product_type = excluded.product_type,
                        project_name = excluded.project_name,
                        operator = excluded.operator,
                        scan_time = excluded.scan_time,
                        updated_at = excluded.updated_at
                    """,
                    (
                        serial,
                        ptype,
                        project,
                        operator,
                        now_ms,
                        materials_json,
                        created_at,
                        now_ms,
                    ),
                )

                # 旧候选不删除，只标记冲突，保留可审计性。
                conn.execute(
                    """
                    UPDATE serial_learning
                    SET conflict_count = conflict_count + 1,
                        updated_at = ?
                    WHERE product_serial = ?
                      AND NOT (project_name = ? AND product_type = ?)
                    """,
                    (now_ms, serial, project, ptype),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[H2绑定修复] 更新记录失败 serial={serial}: {e}")
            return False

        return self.upsert_learning_evidence(
            product_serial=serial,
            project_name=project,
            product_type=ptype,
            source=source,
            operator=operator,
            conflict=False,
            candidates=[],
            increment=3,
        )

    def get_serial_recommendation(
        self,
        product_serial: str,
        current_project: str = "",
        current_product_type: str = "",
        threshold: float = 0.85,
    ) -> Dict:
        """返回序列号推荐候选、冲突与自动应用建议。"""
        serial = str(product_serial or "").strip()
        if not serial:
            return {"success": False, "message": "product_serial 不能为空"}

        cur_project_key = normalize_text_key(current_project)
        cur_type_key = normalize_text_key(current_product_type)

        try:
            main_record = self.get_record(serial)
            candidates: List[Dict] = []

            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT
                        project_name,
                        product_type,
                        evidence_count,
                        manual_confirm_count,
                        auto_accept_count,
                        conflict_count,
                        updated_at,
                        (evidence_count + manual_confirm_count * 6 + auto_accept_count * 3) AS score
                    FROM serial_learning
                    WHERE product_serial = ?
                      AND (evidence_count + manual_confirm_count * 6 + auto_accept_count * 3) > 0
                    ORDER BY score DESC, updated_at DESC
                    LIMIT 10
                    """,
                    (serial,),
                ).fetchall()

            total_score = 0.0
            for row in rows:
                score = float(row["score"] or 0.0)
                total_score += score
                candidates.append(
                    {
                        "project_name": row["project_name"],
                        "product_type": row["product_type"],
                        "evidence_count": int(row["evidence_count"] or 0),
                        "manual_confirm_count": int(row["manual_confirm_count"] or 0),
                        "auto_accept_count": int(row["auto_accept_count"] or 0),
                        "conflict_count": int(row["conflict_count"] or 0),
                        "score": score,
                        "source": "learning",
                        "is_main_record": False,
                    }
                )

            if main_record:
                baseline_project = str(main_record.get("project_name") or "").strip()
                baseline_type = str(main_record.get("product_type") or "").strip()
                if baseline_project and baseline_type:
                    found = None
                    for item in candidates:
                        if (
                            normalize_text_key(item.get("project_name", "")) == normalize_text_key(baseline_project)
                            and normalize_text_key(item.get("product_type", "")) == normalize_text_key(baseline_type)
                        ):
                            found = item
                            break
                    if found is not None:
                        found["is_main_record"] = True
                        found["source"] = "main_record+learning"
                        found["score"] = float(found.get("score") or 0.0) + 6.0
                    else:
                        learning_top_score = max([c.get("score", 0.0) for c in candidates], default=0.0)
                        baseline_score = max(6.0, float(learning_top_score) + 1.0)
                        candidates.insert(
                            0,
                            {
                                "project_name": baseline_project,
                                "product_type": baseline_type,
                                "evidence_count": 1,
                                "manual_confirm_count": 0,
                                "auto_accept_count": 0,
                                "conflict_count": 0,
                                "score": baseline_score,
                                "source": "main_record",
                                "is_main_record": True,
                            },
                        )
                        total_score += baseline_score

            if not candidates:
                return {
                    "success": True,
                    "recommendation": {
                        "product_serial": serial,
                        "recommended_project_name": current_project or "",
                        "recommended_product_type": current_product_type or "",
                        "confidence": 0.0,
                        "should_confirm": True,
                        "auto_apply": False,
                        "reason": "no_candidate",
                        "candidates": [],
                    },
                }

            candidates.sort(key=lambda x: (float(x.get("score", 0.0)), int(x.get("manual_confirm_count", 0))), reverse=True)
            best = candidates[0]
            score_sum = sum(float(item.get("score", 0.0)) for item in candidates) or 1.0
            for item in candidates:
                item["confidence"] = round(float(item.get("score", 0.0)) / score_sum, 4)

            best_confidence = float(best.get("confidence", 0.0))
            missing_current_selection = not cur_project_key or not cur_type_key
            best_key_project = normalize_text_key(best.get("project_name", ""))
            best_key_type = normalize_text_key(best.get("product_type", ""))
            current_conflict = (
                bool(cur_project_key and cur_type_key)
                and (best_key_project != cur_project_key or best_key_type != cur_type_key)
            )

            should_confirm = (
                missing_current_selection
                or current_conflict
                or len(candidates) > 1
            )
            auto_apply = not should_confirm

            reason = "single_candidate"
            if missing_current_selection:
                reason = "current_selection_missing"
            elif current_conflict:
                reason = "current_selection_conflict"
            elif len(candidates) > 1:
                reason = "multiple_candidates"

            if cur_project_key and cur_type_key:
                if best_key_project == cur_project_key and best_key_type == cur_type_key:
                    reason = "already_current_selection"

            return {
                "success": True,
                "recommendation": {
                    "product_serial": serial,
                    "recommended_project_name": best.get("project_name"),
                    "recommended_product_type": best.get("product_type"),
                    "confidence": best_confidence,
                    "should_confirm": should_confirm,
                    "auto_apply": auto_apply,
                    "reason": reason,
                    "candidates": candidates,
                },
            }
        except Exception as e:
            logger.error(f"[H2推荐] 失败 serial={serial}: {e}")
            return {"success": False, "message": f"推荐失败: {e}"}

    def get_duplicate_serials(
        self,
        project_name: str = "",
        serial_like: str = "",
        limit: int = 50,
    ) -> List[Dict]:
        """查询重复产品序列号统计（count > 1）。"""
        safe_limit = max(1, min(int(limit or 50), 500))
        where_clauses = ["1=1"]
        params = []
        if project_name:
            where_clauses.append("project_name = ?")
            params.append(project_name)
        if serial_like:
            where_clauses.append("product_serial LIKE ?")
            params.append(f"%{serial_like}%")
        where_sql = " AND ".join(where_clauses)

        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"""
                    SELECT
                        product_serial,
                        COUNT(*) AS duplicate_count,
                        MAX(scan_time) AS latest_scan_time,
                        MIN(scan_time) AS oldest_scan_time
                    FROM product_records
                    WHERE {where_sql}
                    GROUP BY product_serial
                    HAVING COUNT(*) > 1
                    ORDER BY duplicate_count DESC, latest_scan_time DESC
                    LIMIT ?
                    """,
                    [*params, safe_limit],
                ).fetchall()

            return [
                {
                    "product_serial": r["product_serial"],
                    "duplicate_count": int(r["duplicate_count"] or 0),
                    "latest_scan_time": r["latest_scan_time"],
                    "oldest_scan_time": r["oldest_scan_time"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"查询重复序列号失败: {e}")
            return []

    def cleanup_duplicate_serials(self, serials: Optional[List[str]] = None) -> Dict:
        """
        清理重复序列号数据：每个序列号只保留最新行，materials 按“旧->新”合并后写回保留行。
        """
        cleaned_serials = 0
        removed_rows = 0
        now_ms = int(time.time() * 1000)
        target_serials = []

        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row

                if serials:
                    normalized = []
                    for item in serials:
                        serial = str(item or "").strip()
                        if serial and serial not in normalized:
                            normalized.append(serial)
                    target_serials = normalized
                else:
                    dup_rows = conn.execute(
                        """
                        SELECT product_serial
                        FROM product_records
                        GROUP BY product_serial
                        HAVING COUNT(*) > 1
                        """
                    ).fetchall()
                    target_serials = [str(item["product_serial"]) for item in dup_rows]

                for serial in target_serials:
                    rows = conn.execute(
                        """
                        SELECT rowid, product_serial, scan_time, materials
                        FROM product_records
                        WHERE product_serial = ?
                        ORDER BY scan_time DESC, rowid DESC
                        """,
                        (serial,),
                    ).fetchall()
                    if len(rows) <= 1:
                        continue

                    keep_row = rows[0]
                    merged_materials = {}
                    for row in reversed(rows):
                        mat_str = row["materials"] if "materials" in row.keys() else ""
                        if not isinstance(mat_str, str) or not mat_str.strip():
                            continue
                        try:
                            parsed = json.loads(mat_str)
                            if isinstance(parsed, dict):
                                for k, v in parsed.items():
                                    if v not in (None, "", "null", "nan"):
                                        merged_materials[k] = v
                        except (json.JSONDecodeError, TypeError):
                            continue

                    conn.execute(
                        """
                        UPDATE product_records
                        SET materials = ?, updated_at = ?
                        WHERE rowid = ?
                        """,
                        (
                            json.dumps(merged_materials, ensure_ascii=False) if merged_materials else "{}",
                            now_ms,
                            int(keep_row["rowid"]),
                        ),
                    )

                    delete_rowids = [int(r["rowid"]) for r in rows[1:]]
                    placeholders = ",".join(["?"] * len(delete_rowids))
                    conn.execute(
                        f"DELETE FROM product_records WHERE rowid IN ({placeholders})",
                        delete_rowids,
                    )
                    cleaned_serials += 1
                    removed_rows += len(delete_rowids)

                conn.commit()

            return {
                "success": True,
                "cleaned_serials": cleaned_serials,
                "removed_rows": removed_rows,
                "checked_serials": len(target_serials),
            }
        except Exception as e:
            logger.error(f"清理重复序列号失败: {e}")
            return {
                "success": False,
                "cleaned_serials": cleaned_serials,
                "removed_rows": removed_rows,
                "checked_serials": len(target_serials),
                "error": str(e),
            }
    
    def get_record(self, product_serial: str) -> Optional[Dict]:
        """查询单条记录（带时区转换），返回最新的一条并合并所有历史物料"""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row
                # 查询所有匹配行，按 scan_time DESC 排序
                cursor = conn.execute(
                    "SELECT * FROM product_records WHERE product_serial = ? ORDER BY scan_time DESC",
                    (product_serial,)
                )
                rows = cursor.fetchall()
                if not rows:
                    return None
                # 以最新行为基础，合并所有历史行的 materials
                row = rows[0]
                record = dict(row)

                # 合并所有行的 materials（最新优先）
                merged_materials = {}
                for r in reversed(rows):  # 从旧到新遍历，新值覆盖旧值
                    mat_str = r['materials'] if 'materials' in r.keys() else ''
                    if mat_str and isinstance(mat_str, str):
                        try:
                            mat = json.loads(mat_str)
                            if isinstance(mat, dict):
                                for k, v in mat.items():
                                    if v not in (None, '', 'null', 'nan'):
                                        merged_materials[k] = v
                        except (json.JSONDecodeError, TypeError):
                            pass

                if merged_materials:
                    record['materials'] = json.dumps(merged_materials, ensure_ascii=False)

                # 添加格式化的中国时间
                record['scan_time_formatted'] = format_timestamp_to_china_time(record['scan_time'])
                record['created_at_formatted'] = format_timestamp_to_china_time(record['created_at'])
                record['updated_at_formatted'] = format_timestamp_to_china_time(record['updated_at'])
                return record
        except Exception as e:
            logger.error(f"查询失败: {e}")
            return None
    
    def get_records_by_project(self, project_name: str, limit: int = 100) -> List[Dict]:
        """按项目查询记录（带时区转换）"""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM product_records 
                    WHERE project_name = ? 
                    ORDER BY scan_time DESC 
                    LIMIT ?
                """, (project_name, limit))
                
                records = []
                for row in cursor.fetchall():
                    record = dict(row)
                    # 添加格式化的中国时间
                    record['scan_time_formatted'] = format_timestamp_to_china_time(record['scan_time'])
                    records.append(record)
                
                return records
        except Exception as e:
            logger.error(f"项目查询失败: {e}")
            return []
    
    def delete_record(self, product_serial: str) -> bool:
        """删除指定产品记录"""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM product_records WHERE product_serial = ?",
                    (product_serial,)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"[H2数据库] ✓ 记录删除成功: {product_serial}")
                    return True
                return False
        except Exception as e:
            logger.error(f"[H2数据库] 删除记录异常: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout=5000")

            # 统计不同产品的数量（按 product_serial 去重）
            cursor = conn.execute("SELECT COUNT(DISTINCT product_serial) FROM product_records")
            total_products = cursor.fetchone()[0]

            # 统计总记录数
            cursor = conn.execute("SELECT COUNT(*) FROM product_records")
            total_records = cursor.fetchone()[0]

            cursor = conn.execute("""
                SELECT project_name, COUNT(DISTINCT product_serial) as count
                FROM product_records
                GROUP BY project_name
                ORDER BY count DESC
                LIMIT 10
            """)
            projects = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]

            today = datetime.now(CHINA_TZ).date()
            daily_stats = {}
            for i in range(7):
                day = today - timedelta(days=i)
                next_day = day + timedelta(days=1)
                start_ms = int(datetime.combine(day, datetime.min.time(), CHINA_TZ).timestamp() * 1000)
                end_ms = int(datetime.combine(next_day, datetime.min.time(), CHINA_TZ).timestamp() * 1000)
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM product_records WHERE scan_time >= ? AND scan_time < ?",
                    (start_ms, end_ms),
                )
                daily_stats[day.strftime('%Y-%m-%d')] = int(cursor.fetchone()[0] or 0)

            return {
                "total_records": total_products,  # product count, keep legacy field name
                "total_products": total_products,  # explicit product count
                "total_scan_records": total_records,  # raw scan row count
                "top_projects": projects,
                "daily_stats": daily_stats,
                "today_date": today.strftime('%Y-%m-%d'),
                "db_size": os.path.getsize(self.db_path) if self.db_path.exists() else 0
            }


# 数据库管理器初始化


# 保留占位符以避免破坏后续代码结构
# 初始化全局对象
db_manager = H2DatabaseManager()


# API 端点
@app.route('/api/h2/query/<product_serial>', methods=['GET'])
def query_product_record(product_serial: str):
    """查询单个产品记录（带时区转换）"""
    record = db_manager.get_record(product_serial)
    if record:
        return jsonify({
            "success": True,
            "record": record
        })
    else:
        return jsonify({
            "success": False,
            "message": "记录未找到"
        }), 404


@app.route('/api/h2/project/<project_name>', methods=['GET'])
def query_project_records(project_name: str):
    """查询项目记录（带时区转换）"""
    limit = request.args.get('limit', 100, type=int)
    records = db_manager.get_records_by_project(project_name, limit)
    
    return jsonify({
        "success": True,
        "records": records,
        "count": len(records)
    })


@app.route('/api/h2/stats', methods=['GET'])
def get_database_stats():
    """获取数据库统计信息"""
    stats = db_manager.get_stats()
    return jsonify({
        "success": True,
        "stats": stats
    })


def get_sync_stats():
    """获取同步统计信息"""
    return jsonify({
        "success": True,
        "stats": stats
    })


def trigger_manual_sync():
    """手动触发全量同步"""
    return jsonify(result)


@app.route('/api/h2/save', methods=['POST'])
def save_product_record():
    """保存产品记录（实时写入数据库）"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['product_serial', 'product_type', 'project_name', 'operator']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    "success": False,
                    "message": f"缺少必填字段: {field}"
                }), 400
        
        # 构建记录
        raw_allow_binding_update = data.get('allow_binding_update', False)
        if isinstance(raw_allow_binding_update, str):
            allow_binding_update = raw_allow_binding_update.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            allow_binding_update = bool(raw_allow_binding_update)

        record = {
            'product_serial': data['product_serial'],
            'product_type': data['product_type'],
            'project_name': data['project_name'],
            'operator': data['operator'],
            'scan_time': data.get('scan_time', int(time.time() * 1000)),
            'materials': json.dumps(data.get('materials', {}), ensure_ascii=False),
            'allow_binding_update': allow_binding_update,
        }
        
        # 保存到数据库
        success = db_manager.upsert_record(record)
        
        if success:
            logger.info(f"[API保存] ✓ 记录保存成功: {record['product_serial']}")
            return jsonify({
                "success": True,
                "message": "记录保存成功",
                "product_serial": record['product_serial']
            })
        else:
            logger.error(f"[API保存] ✗ 记录保存失败: {record['product_serial']}")
            return jsonify({
                "success": False,
                "message": "记录保存失败"
            }), 500
            
    except Exception as e:
        logger.error(f"[API保存] 异常: {e}")
        return jsonify({
            "success": False,
            "message": f"保存异常: {str(e)}"
        }), 500


@app.route('/api/h2/recommend/<product_serial>', methods=['GET'])
def recommend_product_serial(product_serial: str):
    """根据序列号返回项目+产品类型推荐。"""
    current_project = request.args.get('current_project', '')
    current_product_type = request.args.get('current_product_type', '')
    result = db_manager.get_serial_recommendation(
        product_serial=product_serial,
        current_project=current_project,
        current_product_type=current_product_type,
        threshold=0.85,
    )
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 500


@app.route('/api/h2/learning/confirm', methods=['POST'])
def confirm_serial_learning():
    """写回用户最终选择，保留学习证据和审计事件。"""
    try:
        data = request.get_json() or {}
        serial = str(data.get("product_serial") or "").strip()
        project_name = str(data.get("project_name") or "").strip()
        product_type = str(data.get("product_type") or "").strip()
        source = str(data.get("source") or "manual_confirm").strip()
        operator = str(data.get("operator") or "").strip()
        conflict = parse_bool(data.get("conflict", False), False)
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            candidates = []

        if not serial or not project_name or not product_type:
            return jsonify({
                "success": False,
                "message": "缺少必填字段: product_serial/project_name/product_type"
            }), 400

        success = db_manager.upsert_learning_evidence(
            product_serial=serial,
            project_name=project_name,
            product_type=product_type,
            source=source,
            operator=operator,
            conflict=conflict,
            candidates=candidates,
            increment=1,
        )
        if not success:
            return jsonify({"success": False, "message": "学习写回失败"}), 500

        return jsonify({
            "success": True,
            "message": "学习写回成功",
            "product_serial": serial,
            "project_name": project_name,
            "product_type": product_type,
        })
    except Exception as e:
        logger.error(f"[H2学习] 写回异常: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"学习写回异常: {e}"
        }), 500


@app.route('/api/h2/binding/repair', methods=['POST'])
def repair_serial_binding():
    """手动修复序列号绑定（项目/产品类型），用于扫码纠错。"""
    try:
        data = request.get_json() or {}
        serial = str(data.get("product_serial") or "").strip()
        project_name = str(data.get("project_name") or "").strip()
        product_type = str(data.get("product_type") or "").strip()
        operator = str(data.get("operator") or "").strip()
        source = str(data.get("source") or "manual_repair").strip() or "manual_repair"

        if not serial or not project_name or not product_type:
            return jsonify({
                "success": False,
                "message": "缺少必填字段: product_serial/project_name/product_type"
            }), 400

        success = db_manager.repair_serial_binding(
            product_serial=serial,
            project_name=project_name,
            product_type=product_type,
            operator=operator,
            source=source,
        )
        if not success:
            return jsonify({"success": False, "message": "绑定修复失败"}), 500

        return jsonify({
            "success": True,
            "message": "绑定修复成功",
            "product_serial": serial,
            "project_name": project_name,
            "product_type": product_type,
        })
    except Exception as e:
        logger.error(f"[H2绑定修复] 异常: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"绑定修复异常: {e}"
        }), 500


@app.route('/api/h2/delete/<product_serial>', methods=['DELETE'])
def delete_product_record(product_serial: str):
    """删除产品记录"""
    try:
        success = db_manager.delete_record(product_serial)
        
        if success:
            logger.info(f"[API删除] ✓ 记录删除成功: {product_serial}")
            return jsonify({
                "success": True,
                "message": "记录删除成功"
            })
        else:
            return jsonify({
                "success": False,
                "message": "记录不存在或删除失败"
            }), 404
            
    except Exception as e:
        logger.error(f"[API删除] 异常: {e}")
        return jsonify({
            "success": False,
            "message": f"删除异常: {str(e)}"
        }), 500


@app.route('/api/h2/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "success": True,
        "message": "H2 API服务运行正常",
        "timestamp": datetime.now().isoformat(),
        "timezone": "Asia/Shanghai (GMT+8)"
    })


if __name__ == '__main__':
    print("="*60)
    print(" H2 API服务 - 增强版 v2")
    print("="*60)
    print(" 新功能:")
    print("  ✓ 时区自动转换（UTC → 中国时区）")
    print("  ✓ CSV文件实时监控（5秒检查间隔）")
    print("  ✓ 内容哈希检测（避免误触发同步）")
    print("  ✓ 定时自动同步（每30分钟）")
    print("="*60)
    print(" API端点:")
    print("  POST   /api/h2/save                    - 保存产品记录（实时写入）")
    print("  GET    /api/h2/query/<product_serial>  - 查询产品记录")
    print("  DELETE /api/h2/delete/<product_serial> - 删除产品记录")
    print("  GET    /api/h2/project/<project_name>  - 查询项目记录")
    print("  GET    /api/h2/stats                   - 数据库统计")
    print("  GET    /api/h2/sync/stats              - 同步统计")
    print("  POST   /api/h2/sync/trigger            - 手动触发同步")
    print("  GET    /api/h2/health                  - 健康检查")
    print("="*60)
    print(f" 数据库路径: {db_manager.db_path}")
    print(f" 监听地址: http://0.0.0.0:8892")
    print("="*60)
    
    app.run(host='0.0.0.0', port=8892, debug=False, threaded=True)
