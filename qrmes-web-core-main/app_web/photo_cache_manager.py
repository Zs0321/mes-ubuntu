#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
照片缓存管理器
使用后端缓存减少浏览器内存占用
"""

import os
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from PIL import Image
import logging

logger = logging.getLogger(__name__)

class PhotoCacheManager:
    """照片缓存管理器"""
    
    def __init__(self, cache_dir: str = 'cache/photos', max_cache_size_mb: int = 500):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录路径
            max_cache_size_mb: 最大缓存大小(MB)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.thumbnail_dir = self.cache_dir / 'thumbnails'
        self.thumbnail_dir.mkdir(exist_ok=True)
        
        self.compressed_dir = self.cache_dir / 'compressed'
        self.compressed_dir.mkdir(exist_ok=True)
        
        self.max_cache_size = max_cache_size_mb * 1024 * 1024
        self.cache_index = {}  # 缓存索引 {file_path: cache_info}
        
        # 损坏图片黑名单 - 避免重复尝试处理
        self.failed_images_file = self.cache_dir / 'failed_images.txt'
        self.failed_images = self._load_failed_images()
        
        logger.info(f"照片缓存管理器初始化完成: {cache_dir}, 最大缓存: {max_cache_size_mb}MB")
    
    def _load_failed_images(self) -> set:
        """加载失败图片列表"""
        failed = set()
        if self.failed_images_file.exists():
            try:
                with open(self.failed_images_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            failed.add(line)
                logger.info(f"加载失败图片黑名单: {len(failed)} 个")
            except Exception as e:
                logger.error(f"加载失败图片列表失败: {e}")
        return failed

    def _failed_image_token(self, image_path: Path) -> str:
        """为失败记录生成带版本的 token，文件变化后可自动失效。"""
        stat = image_path.stat()
        return f"{image_path}|{stat.st_mtime_ns}|{stat.st_size}"

    def _persist_failed_images(self):
        """将内存中的失败列表回写到文件。"""
        try:
            entries = sorted(self.failed_images)
            with open(self.failed_images_file, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(f"{entry}\n")
        except Exception as e:
            logger.error(f"持久化失败图片列表失败: {e}")
    
    def _save_failed_image(self, image_path: Path):
        """记录失败的图片"""
        try:
            try:
                token = self._failed_image_token(image_path)
            except Exception:
                token = str(image_path)

            if token not in self.failed_images:
                self.failed_images.discard(str(image_path))
                self.failed_images.add(token)
                with open(self.failed_images_file, 'a', encoding='utf-8') as f:
                    f.write(f"{token}\n")
                logger.debug(f"记录失败图片: {image_path.name}")
        except Exception as e:
            logger.error(f"保存失败图片记录失败: {e}")
    
    def is_failed_image(self, image_path: Path) -> bool:
        """检查图片是否在失败黑名单中"""
        path_str = str(image_path)

        try:
            token = self._failed_image_token(image_path)
        except Exception:
            token = path_str

        if token in self.failed_images:
            return True

        # 兼容旧版只按路径记录的黑名单：如果文件已经恢复且非空，则自动解除。
        if path_str in self.failed_images:
            try:
                stat = image_path.stat()
            except Exception:
                return True

            if stat.st_size <= 0:
                return True

            self.failed_images.discard(path_str)
            self._persist_failed_images()
            logger.info(f"移除已恢复的失败图片旧记录: {image_path.name}")
            return False

        return False
    
    def get_file_hash(self, file_path: Path) -> str:
        """获取文件哈希值"""
        stat = file_path.stat()
        # 使用文件路径+修改时间+大小作为哈希依据
        hash_str = f"{file_path}_{stat.st_mtime}_{stat.st_size}"
        return hashlib.md5(hash_str.encode()).hexdigest()
    
    def get_thumbnail(self, image_path: Path, size: tuple = (300, 300)) -> Optional[Path]:
        """
        获取缩略图，如果不存在则生成
        
        Args:
            image_path: 原始图片路径
            size: 缩略图尺寸
            
        Returns:
            缩略图路径，失败返回None
        """
        try:
            if not image_path.exists():
                logger.warning(f"原始图片不存在: {image_path}")
                return None
            
            # 检查是否在失败黑名单中
            if self.is_failed_image(image_path):
                logger.debug(f"跳过失败图片: {image_path.name}")
                return None
            
            # 生成缓存文件名
            file_hash = self.get_file_hash(image_path)
            thumbnail_name = f"thumb_{file_hash}_{size[0]}x{size[1]}.jpg"
            thumbnail_path = self.thumbnail_dir / thumbnail_name
            
            # 检查缓存是否存在且有效
            if thumbnail_path.exists():
                # 检查原图是否被修改
                if thumbnail_path.stat().st_mtime > image_path.stat().st_mtime:
                    logger.debug(f"使用缓存的缩略图: {thumbnail_name}")
                    return thumbnail_path
            
            # 生成新缩略图
            logger.info(f"生成缩略图: {image_path.name}")
            with Image.open(image_path) as img:
                # 转换为RGB模式（处理RGBA等格式）
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 生成缩略图
                img.thumbnail(size, Image.Resampling.LANCZOS)
                img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
            
            # 更新缓存索引
            self.cache_index[str(image_path)] = {
                'thumbnail': str(thumbnail_path),
                'size': thumbnail_path.stat().st_size,
                'created_at': time.time()
            }
            
            # 检查缓存大小
            self._check_cache_size()
            
            return thumbnail_path
            
        except Exception as e:
            logger.error(f"生成缩略图失败: {e}")
            # 记录到失败黑名单
            self._save_failed_image(image_path)
            return None
    
    def get_compressed_image(self, image_path: Path, max_width: int = 1200, 
                           quality: int = 85) -> Optional[Path]:
        """
        获取压缩后的图片，用于Web显示
        
        Args:
            image_path: 原始图片路径
            max_width: 最大宽度
            quality: JPEG质量(1-100)
            
        Returns:
            压缩图片路径，失败返回None
        """
        try:
            if not image_path.exists():
                return None
            
            # 检查是否在失败黑名单中
            if self.is_failed_image(image_path):
                logger.debug(f"跳过失败图片: {image_path.name}")
                return None
            
            # 生成缓存文件名
            file_hash = self.get_file_hash(image_path)
            compressed_name = f"comp_{file_hash}_{max_width}_{quality}.jpg"
            compressed_path = self.compressed_dir / compressed_name
            
            # 检查缓存
            if compressed_path.exists():
                if compressed_path.stat().st_mtime > image_path.stat().st_mtime:
                    return compressed_path
            
            # 生成压缩图片
            logger.info(f"压缩图片: {image_path.name}")
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 如果图片宽度大于max_width，则缩放
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                
                img.save(compressed_path, 'JPEG', quality=quality, optimize=True)
            
            # 更新缓存索引
            self.cache_index[str(image_path)] = {
                **self.cache_index.get(str(image_path), {}),
                'compressed': str(compressed_path),
                'compressed_size': compressed_path.stat().st_size,
                'updated_at': time.time()
            }
            
            self._check_cache_size()
            
            return compressed_path
            
        except Exception as e:
            logger.error(f"压缩图片失败: {e}")
            # 记录到失败黑名单
            self._save_failed_image(image_path)
            return None
    
    def _check_cache_size(self):
        """检查并清理缓存"""
        try:
            # 计算当前缓存大小
            total_size = 0
            cache_files = []
            
            for cache_subdir in [self.thumbnail_dir, self.compressed_dir]:
                for file_path in cache_subdir.glob('*'):
                    if file_path.is_file():
                        stat = file_path.stat()
                        total_size += stat.st_size
                        cache_files.append({
                            'path': file_path,
                            'size': stat.st_size,
                            'atime': stat.st_atime  # 访问时间
                        })
            
            # 如果超过限制，删除最久未访问的文件
            if total_size > self.max_cache_size:
                logger.info(f"缓存大小超限: {total_size / (1024*1024):.2f}MB, 开始清理")
                
                # 按访问时间排序
                cache_files.sort(key=lambda x: x['atime'])
                
                # 删除文件直到低于限制的80%
                target_size = self.max_cache_size * 0.8
                for file_info in cache_files:
                    if total_size <= target_size:
                        break
                    
                    file_path = file_info['path']
                    file_path.unlink()
                    total_size -= file_info['size']
                    logger.debug(f"删除缓存文件: {file_path.name}")
                
                logger.info(f"缓存清理完成: {total_size / (1024*1024):.2f}MB")
                
        except Exception as e:
            logger.error(f"检查缓存大小失败: {e}")
    
    def clear_cache(self):
        """清空所有缓存"""
        try:
            for cache_subdir in [self.thumbnail_dir, self.compressed_dir]:
                for file_path in cache_subdir.glob('*'):
                    if file_path.is_file():
                        file_path.unlink()
            
            self.cache_index.clear()
            logger.info("缓存已清空")
            
        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
    
    def clear_failed_images_list(self):
        """清空失败图片黑名单，允许重试"""
        try:
            self.failed_images.clear()
            if self.failed_images_file.exists():
                self.failed_images_file.unlink()
            logger.info("失败图片黑名单已清空")
        except Exception as e:
            logger.error(f"清空失败图片列表失败: {e}")
    
    def get_failed_images_list(self) -> List[str]:
        """获取失败图片列表"""
        return list(self.failed_images)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            thumbnail_count = len(list(self.thumbnail_dir.glob('*')))
            compressed_count = len(list(self.compressed_dir.glob('*')))
            
            total_size = 0
            for cache_subdir in [self.thumbnail_dir, self.compressed_dir]:
                for file_path in cache_subdir.glob('*'):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
            
            return {
                'thumbnail_count': thumbnail_count,
                'compressed_count': compressed_count,
                'total_size_mb': total_size / (1024 * 1024),
                'max_size_mb': self.max_cache_size / (1024 * 1024),
                'usage_percent': (total_size / self.max_cache_size * 100) if self.max_cache_size > 0 else 0,
                'failed_images_count': len(self.failed_images)
            }
            
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {}
