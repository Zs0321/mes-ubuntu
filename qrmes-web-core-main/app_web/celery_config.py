"""
异步任务配置 - Celery 任务队列

用于后台照片处理、批量操作等异步任务
"""

import os
from celery import Celery

# 创建 Celery 应用
celery_app = Celery(
    'qrscanner',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,

    # 任务结果过期时间（1小时）
    result_expires=3600,

    # 任务超时设置
    task_soft_time_limit=300,  # 5分钟软限制
    task_time_limit=600,  # 10分钟硬限制

    # 任务重试设置
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # 并发设置
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,

    # 任务路由
    task_routes={
        'tasks.photo.*': {'queue': 'photo_processing'},
        'tasks.batch.*': {'queue': 'batch_operations'},
        'tasks.analysis.*': {'queue': 'analysis'},
    },

    # 任务优先级
    task_default_priority=5,
    task_queue_max_priority=10,
)

# 自动发现任务
celery_app.autodiscover_tasks(['tasks'])

__all__ = ['celery_app']
