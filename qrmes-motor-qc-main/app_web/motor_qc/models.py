"""Motor QC 数据模型"""
import sqlite3
from datetime import datetime
from pathlib import Path
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, UniqueConstraint, ForeignKey, event, inspect, text

# SQLAlchemy instance
db = SQLAlchemy()

class MotorQCDatabase:
    """Motor QC 数据库管理"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 电机记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS motor_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                serial_number TEXT NOT NULL,
                overall_status TEXT DEFAULT 'pending',
                total_processes INTEGER DEFAULT 0,
                completed_processes INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, serial_number)
            )
        ''')

        # 质检记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL,
                serial_number TEXT NOT NULL,
                process_id INTEGER NOT NULL,
                process_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                confidence REAL DEFAULT 0.0,
                issues TEXT,
                summary TEXT,
                photos TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                analyzed_at TIMESTAMP
            )
        ''')

        # 照片记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id TEXT UNIQUE NOT NULL,
                inspection_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inspection_id) REFERENCES inspections(inspection_id)
            )
        ''')

        # 性能优化：添加索引
        # 照片表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_photos_inspection_id
            ON photos(inspection_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_photos_uploaded_at
            ON photos(uploaded_at DESC)
        ''')

        # 质检表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_inspections_project_serial
            ON inspections(project_id, serial_number)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_inspections_created_at
            ON inspections(created_at DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_inspections_status
            ON inspections(status)
        ''')

        # 电机记录表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_motor_records_project_id
            ON motor_records(project_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_motor_records_created_at
            ON motor_records(created_at DESC)
        ''')

        conn.commit()
        conn.close()

    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


# SQLAlchemy Models

class InspectionRecord(db.Model):
    """质检记录模型"""
    __tablename__ = 'inspection_records'

    id = db.Column(db.Integer, primary_key=True)
    project_code = db.Column(db.String(100), nullable=False, index=True)
    process_step = db.Column(db.String(100), nullable=False)
    photo_path = db.Column(db.String(500), nullable=False)
    inspector_id = db.Column(db.String(100), nullable=False)
    inspection_result = db.Column(db.Text)
    defects_found = db.Column(JSON)  # Store as JSON array
    status = db.Column(db.String(50), default='pending')
    # 双轨结论：保留 AI 原始结论，同时记录人工复核覆盖结论
    ai_status = db.Column(db.String(50))
    ai_summary = db.Column(db.Text)
    ai_defects = db.Column(JSON)
    human_status = db.Column(db.String(50))
    human_summary = db.Column(db.Text)
    human_defects = db.Column(JSON)
    human_confirmed_by = db.Column(db.String(100))
    human_confirmed_at = db.Column(db.DateTime)
    inspected_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<InspectionRecord {self.id} - {self.project_code}/{self.process_step}>'


class QCExperienceBucket(db.Model):
    """QC 经验桶：按层级组织规则（global/cooling/platform/model）。"""

    __tablename__ = 'qc_experience_buckets'
    __table_args__ = (
        UniqueConstraint(
            'bucket_key',
            name='uq_qc_experience_bucket_key',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    scope_level = db.Column(db.String(20), nullable=False, index=True)  # global/cooling/platform/model
    bucket_key = db.Column(db.String(256), nullable=False, index=True)
    stator_platform = db.Column(db.String(32), nullable=True, index=True)  # TZ180
    cooling_type = db.Column(db.String(16), nullable=True, index=True)  # OIL/WATER/AIR/NATURAL
    model_code = db.Column(db.String(128), nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    rules = db.relationship('QCExperienceRule', backref='bucket', lazy='dynamic')
    feedback_records = db.relationship('QCFeedbackRecord', backref='bucket', lazy='dynamic')

    def to_dict(self):
        return {
            "id": self.id,
            "scope_level": self.scope_level,
            "bucket_key": self.bucket_key,
            "stator_platform": self.stator_platform,
            "cooling_type": self.cooling_type,
            "model_code": self.model_code,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QCExperienceRule(db.Model):
    """QC 经验规则。"""

    __tablename__ = 'qc_experience_rules'

    id = db.Column(db.Integer, primary_key=True)
    bucket_id = db.Column(
        db.Integer,
        ForeignKey('qc_experience_buckets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    process_name = db.Column(db.String(128), nullable=False, index=True)
    rule_type = db.Column(db.String(32), nullable=False, default='prompt')
    rule_payload = db.Column(JSON, nullable=False, default=dict)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    confirmed_count = db.Column(db.Integer, nullable=False, default=0)
    corrected_count = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    effective_from = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "bucket_id": self.bucket_id,
            "process_name": self.process_name,
            "rule_type": self.rule_type,
            "rule_payload": self.rule_payload or {},
            "confidence": self.confidence,
            "confirmed_count": self.confirmed_count,
            "corrected_count": self.corrected_count,
            "version": self.version,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "is_active": self.is_active,
        }


class QCFeedbackRecord(db.Model):
    """人工确认/改判记录。"""

    __tablename__ = 'qc_feedback_records'

    id = db.Column(db.Integer, primary_key=True)
    bucket_id = db.Column(
        db.Integer,
        ForeignKey('qc_experience_buckets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    rule_id = db.Column(
        db.Integer,
        ForeignKey('qc_experience_rules.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    project_id = db.Column(db.String(128), nullable=False, index=True)
    serial_number = db.Column(db.String(128), nullable=False, index=True)
    process_name = db.Column(db.String(128), nullable=False, index=True)
    ai_result = db.Column(db.String(32), nullable=True)
    human_result = db.Column(db.String(32), nullable=False)
    defect_tags = db.Column(JSON, nullable=False, default=list)
    image_refs = db.Column(JSON, nullable=False, default=list)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.String(128), nullable=False, default='unknown')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    rule = db.relationship('QCExperienceRule', backref='feedback_records')

    def is_corrected(self) -> bool:
        return bool((self.ai_result or "").strip()) and (self.ai_result or "").strip().lower() != (
            self.human_result or ""
        ).strip().lower()

    def to_dict(self):
        return {
            "id": self.id,
            "bucket_id": self.bucket_id,
            "rule_id": self.rule_id,
            "project_id": self.project_id,
            "serial_number": self.serial_number,
            "process_name": self.process_name,
            "ai_result": self.ai_result,
            "human_result": self.human_result,
            "defect_tags": self.defect_tags or [],
            "image_refs": self.image_refs or [],
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_corrected": self.is_corrected(),
        }


class QCRulePromotion(db.Model):
    """规则升级记录（如 platform -> cooling/global）。"""

    __tablename__ = 'qc_rule_promotions'

    id = db.Column(db.Integer, primary_key=True)
    from_bucket_id = db.Column(
        db.Integer,
        ForeignKey('qc_experience_buckets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    to_bucket_id = db.Column(
        db.Integer,
        ForeignKey('qc_experience_buckets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    reason = db.Column(db.String(500), nullable=True)
    sample_count = db.Column(db.Integer, nullable=False, default=0)
    quality_score = db.Column(db.Float, nullable=True)
    approved_by = db.Column(db.String(128), nullable=False, default='unknown')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    from_bucket = db.relationship('QCExperienceBucket', foreign_keys=[from_bucket_id], backref='promotions_from')
    to_bucket = db.relationship('QCExperienceBucket', foreign_keys=[to_bucket_id], backref='promotions_to')

    def to_dict(self):
        return {
            "id": self.id,
            "from_bucket_id": self.from_bucket_id,
            "to_bucket_id": self.to_bucket_id,
            "reason": self.reason,
            "sample_count": self.sample_count,
            "quality_score": self.quality_score,
            "approved_by": self.approved_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class QCProcessTask(db.Model):
    """工序级QC任务。唯一维度：project_id + serial_number + process_name。"""

    __tablename__ = "qc_process_tasks"
    __table_args__ = (
        UniqueConstraint("task_key", name="uq_qc_process_tasks_task_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    task_key = db.Column(db.String(256), nullable=False, index=True)
    project_id = db.Column(db.String(128), nullable=False, index=True)
    serial_number = db.Column(db.String(128), nullable=False, index=True)
    product_type = db.Column(db.String(128), nullable=True, index=True)
    process_name = db.Column(db.String(128), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    photo_count = db.Column(db.Integer, nullable=False, default=0)
    latest_photo_path = db.Column(db.String(500), nullable=True)
    best_result_json = db.Column(JSON, nullable=False, default=dict)
    error_message = db.Column(db.Text, nullable=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    claimed_by = db.Column(db.String(128), nullable=True)
    claimed_at = db.Column(db.DateTime, nullable=True, index=True)
    last_analyzed_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    photos = db.relationship("QCTaskPhoto", backref="task", lazy="dynamic", cascade="all, delete-orphan")
    detail_items = db.relationship("QCTaskDetailItem", backref="task", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "task_key": self.task_key,
            "project_id": self.project_id,
            "serial_number": self.serial_number,
            "product_type": self.product_type,
            "process_name": self.process_name,
            "status": self.status,
            "photo_count": self.photo_count,
            "latest_photo_path": self.latest_photo_path,
            "best_result_json": self.best_result_json or {},
            "error_message": self.error_message,
            "attempt_count": self.attempt_count,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "last_analyzed_at": self.last_analyzed_at.isoformat() if self.last_analyzed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QCTaskPhoto(db.Model):
    """任务关联照片（单图识别输入与结果）。"""

    __tablename__ = "qc_task_photos"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer,
        ForeignKey("qc_process_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    photo_path = db.Column(db.String(500), nullable=False)
    photo_name = db.Column(db.String(255), nullable=True)
    captured_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    analyzed_at = db.Column(db.DateTime, nullable=True, index=True)
    analysis_json = db.Column(JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "photo_path": self.photo_path,
            "photo_name": self.photo_name,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
            "analysis_json": self.analysis_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class QCTaskDetailItem(db.Model):
    """任务细节项（配置项优先，AI补充项次之）。"""

    __tablename__ = "qc_task_detail_items"
    __table_args__ = (
        UniqueConstraint("task_id", "detail_key", name="uq_qc_task_detail_items_task_detail_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer,
        ForeignKey("qc_process_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    detail_key = db.Column(db.String(128), nullable=False, index=True)
    detail_label = db.Column(db.String(255), nullable=False)
    source = db.Column(db.String(32), nullable=False, default="config", index=True)  # config/ai
    best_status = db.Column(db.String(32), nullable=False, default="pending", index=True)  # pass/fail/pending
    best_photo_id = db.Column(
        db.Integer,
        ForeignKey("qc_task_photos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confirmed_status = db.Column(db.String(32), nullable=True, index=True)
    confirmed_by = db.Column(db.String(128), nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    best_photo = db.relationship("QCTaskPhoto", foreign_keys=[best_photo_id])

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "detail_key": self.detail_key,
            "detail_label": self.detail_label,
            "source": self.source,
            "best_status": self.best_status,
            "best_photo_id": self.best_photo_id,
            "confirmed_status": self.confirmed_status,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def build_bucket_key(scope_level: str, stator_platform: str = "", cooling_type: str = "", model_code: str = "") -> str:
    level = (scope_level or "").strip().lower()
    platform = (stator_platform or "").strip().upper()
    cooling = (cooling_type or "").strip().upper()
    model = (model_code or "").strip()

    if level == "model":
        return f"model:{platform}:{cooling}:{model}"
    if level == "platform":
        return f"platform:{platform}:{cooling}"
    if level == "cooling":
        return f"cooling:{cooling}"
    if level == "unknown":
        return "unknown"
    return "global"


@event.listens_for(QCExperienceBucket, "before_insert")
def _bucket_before_insert(_mapper, _connection, target):
    target.scope_level = (target.scope_level or "").strip().lower()
    target.stator_platform = ((target.stator_platform or "").strip().upper() or None)
    target.cooling_type = ((target.cooling_type or "").strip().upper() or None)
    target.model_code = ((target.model_code or "").strip() or None)
    target.bucket_key = build_bucket_key(
        target.scope_level,
        target.stator_platform or "",
        target.cooling_type or "",
        target.model_code or "",
    )


@event.listens_for(QCExperienceBucket, "before_update")
def _bucket_before_update(_mapper, _connection, target):
    target.scope_level = (target.scope_level or "").strip().lower()
    target.stator_platform = ((target.stator_platform or "").strip().upper() or None)
    target.cooling_type = ((target.cooling_type or "").strip().upper() or None)
    target.model_code = ((target.model_code or "").strip() or None)
    state = inspect(target)
    semantic_changed = any(
        state.attrs[field].history.has_changes()
        for field in ("scope_level", "stator_platform", "cooling_type", "model_code")
    )
    current_key = (target.bucket_key or "").strip()

    # 兼容迁移阶段生成的去重 key（如 global#12）：仅在语义字段变化时重算 key。
    if semantic_changed or not current_key:
        target.bucket_key = build_bucket_key(
            target.scope_level,
            target.stator_platform or "",
            target.cooling_type or "",
            target.model_code or "",
        )


def ensure_qc_experience_schema_compatibility(logger=None):
    """
    兼容旧版本库结构：
    - 若 qc_experience_buckets 缺少 bucket_key 列则自动补齐并回填
    - 补齐 bucket_key 唯一索引
    """
    engine = db.engine
    inspector = inspect(engine)
    if not inspector.has_table("qc_experience_buckets"):
        return

    with engine.begin() as conn:
        columns = {
            str(row[1])
            for row in conn.execute(text("PRAGMA table_info(qc_experience_buckets)")).fetchall()
            if len(row) >= 2 and row[1]
        }

        if "bucket_key" not in columns:
            conn.execute(text("ALTER TABLE qc_experience_buckets ADD COLUMN bucket_key VARCHAR(256)"))
            if logger:
                logger.info("[MotorQC] 已为 qc_experience_buckets 添加 bucket_key 列")

        rows = conn.execute(
            text(
                "SELECT id, scope_level, stator_platform, cooling_type, model_code, bucket_key "
                "FROM qc_experience_buckets"
            )
        ).fetchall()
        used_keys = set()
        for row in rows:
            rid = int(row[0])
            scope_level = str(row[1] or "")
            stator_platform = str(row[2] or "")
            cooling_type = str(row[3] or "")
            model_code = str(row[4] or "")
            existing_key = str(row[5] or "").strip()

            candidate_key = existing_key or build_bucket_key(scope_level, stator_platform, cooling_type, model_code)
            if candidate_key in used_keys:
                candidate_key = f"{candidate_key}#{rid}"
            used_keys.add(candidate_key)

            if existing_key != candidate_key:
                conn.execute(
                    text("UPDATE qc_experience_buckets SET bucket_key = :bucket_key WHERE id = :id"),
                    {"bucket_key": candidate_key, "id": rid},
                )

        try:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_qc_experience_buckets_bucket_key "
                    "ON qc_experience_buckets(bucket_key)"
                )
            )
        except Exception as exc:
            if logger:
                logger.warning(f"[MotorQC] 创建 bucket_key 唯一索引失败: {exc}")


def ensure_qc_task_schema_compatibility(logger=None):
    """
    兼容任务中心表结构：
    - 如果是旧库（缺表）则创建任务相关表
    - 补齐关键索引（幂等）
    """
    engine = db.engine
    inspector = inspect(engine)

    table_classes = [QCProcessTask.__table__, QCTaskPhoto.__table__, QCTaskDetailItem.__table__]
    for table in table_classes:
        if not inspector.has_table(table.name):
            table.create(bind=engine, checkfirst=True)
            if logger:
                logger.info(f"[MotorQC] 已创建任务表: {table.name}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_qc_process_tasks_status_updated "
                "ON qc_process_tasks(status, updated_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_qc_process_tasks_project_serial_process "
                "ON qc_process_tasks(project_id, serial_number, process_name)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_qc_task_photos_task_captured "
                "ON qc_task_photos(task_id, captured_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_qc_task_detail_items_task_source "
                "ON qc_task_detail_items(task_id, source)"
            )
        )


def ensure_qc_inspection_schema_compatibility(logger=None):
    """
    兼容 inspection_records 双轨结论字段：
    - ai_status/ai_summary/ai_defects
    - human_status/human_summary/human_defects/human_confirmed_by/human_confirmed_at
    """
    engine = db.engine
    inspector = inspect(engine)
    if not inspector.has_table("inspection_records"):
        return

    required_columns = {
        "ai_status": "VARCHAR(50)",
        "ai_summary": "TEXT",
        "ai_defects": "TEXT",
        "human_status": "VARCHAR(50)",
        "human_summary": "TEXT",
        "human_defects": "TEXT",
        "human_confirmed_by": "VARCHAR(100)",
        "human_confirmed_at": "DATETIME",
    }

    with engine.begin() as conn:
        columns = {
            str(row[1])
            for row in conn.execute(text("PRAGMA table_info(inspection_records)")).fetchall()
            if len(row) >= 2 and row[1]
        }
        for column_name, column_type in required_columns.items():
            if column_name in columns:
                continue
            conn.execute(
                text(f"ALTER TABLE inspection_records ADD COLUMN {column_name} {column_type}")
            )
            if logger:
                logger.info(f"[MotorQC] 已为 inspection_records 添加列: {column_name}")
