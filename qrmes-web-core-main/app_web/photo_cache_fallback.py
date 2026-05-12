#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
照片缓存降级策略
当缓存生成失败时，提供原图访问
"""

from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class PhotoCacheFallback:
    """照片缓存降级处理器"""
    
    @staticmethod
    def get_photo_with_fallback(cache_manager, image_path: Path, 
                                cache_type: str = 'thumbnail',
                                **kwargs) -> tuple:
        """
        获取照片，支持降级到原图
        
        Args:
            cache_manager: PhotoCacheManager 实例
            image_path: 原始图片路径
            cache_type: 'thumbnail' 或 'compressed'
            **kwargs: 传递给缓存方法的参数
            
        Returns:
            (file_path, is_cached, error_msg)
            - file_path: 文件路径（缓存或原图）
            - is_cached: 是否使用了缓存
            - error_msg: 错误信息（如果有）
        """
        if not image_path.exists():
            return None, False, "原始图片不存在"
        
        # 尝试获取缓存
        try:
            if cache_type == 'thumbnail':
                cached_path = cache_manager.get_thumbnail(
                    image_path, 
                    size=kwargs.get('size', (300, 300))
                )
            elif cache_type == 'compressed':
                cached_path = cache_manager.get_compressed_image(
                    image_path,
                    max_width=kwargs.get('max_width', 1200),
                    quality=kwargs.get('quality', 85)
                )
            else:
                return None, False, f"未知的缓存类型: {cache_type}"
            
            # 如果缓存成功
            if cached_path and cached_path.exists():
                logger.debug(f"使用缓存: {cached_path.name}")
                return cached_path, True, None
            
            # 缓存失败，降级到原图
            logger.warning(f"缓存失败，使用原图: {image_path.name}")
            return image_path, False, "缓存生成失败，使用原图"
            
        except Exception as e:
            logger.error(f"获取照片失败: {e}")
            # 降级到原图
            return image_path, False, f"处理失败: {str(e)}"
    
    @staticmethod
    def get_thumbnail_with_fallback(cache_manager, image_path: Path, 
                                   size: tuple = (300, 300)) -> tuple:
        """获取缩略图，失败时返回原图"""
        return PhotoCacheFallback.get_photo_with_fallback(
            cache_manager, image_path, 'thumbnail', size=size
        )
    
    @staticmethod
    def get_compressed_with_fallback(cache_manager, image_path: Path,
                                    max_width: int = 1200, 
                                    quality: int = 85) -> tuple:
        """获取压缩图，失败时返回原图"""
        return PhotoCacheFallback.get_photo_with_fallback(
            cache_manager, image_path, 'compressed', 
            max_width=max_width, quality=quality
        )
