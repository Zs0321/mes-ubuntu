"""
照片管理模块

提供照片上传、查询、缓存和索引功能的统一接口
"""

from flask import Blueprint

# 创建照片模块的 Blueprint
photos_bp = Blueprint('photos', __name__, url_prefix='/api/photos')

# 导入路由（避免循环导入）
from . import routes

__all__ = ['photos_bp']
