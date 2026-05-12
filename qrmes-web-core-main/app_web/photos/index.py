"""
照片索引管理 - 照片文件扫描和索引

保留现有的 photo_index.py 功能
"""

import sys
from pathlib import Path

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入现有照片索引
from photo_index import *

__all__ = ['ScanFilters']
