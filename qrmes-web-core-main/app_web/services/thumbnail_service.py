"""缩略图生成服务"""
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
import logging
import hashlib

logger = logging.getLogger(__name__)


class ThumbnailService:
    """缩略图生成服务"""

    # 缩略图尺寸
    THUMBNAIL_SIZES = {
        'small': (150, 150),
        'medium': (300, 300),
        'large': (600, 600),
    }

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, image_path: str, size: str) -> Path:
        """生成缩略图缓存路径"""
        # 使用原图路径的 hash 作为缓存文件名
        path_hash = hashlib.md5(image_path.encode()).hexdigest()
        return self.cache_dir / f"{path_hash}_{size}.jpg"

    def get_thumbnail(
        self,
        image_path: str,
        size: str = 'medium',
        force_regenerate: bool = False
    ) -> Optional[Path]:
        """
        获取缩略图

        Args:
            image_path: 原图路径
            size: 缩略图尺寸 (small/medium/large)
            force_regenerate: 强制重新生成

        Returns:
            缩略图路径，失败返回 None
        """
        if size not in self.THUMBNAIL_SIZES:
            logger.warning(f"不支持的缩略图尺寸: {size}")
            return None

        # 检查原图是否存在
        original_path = Path(image_path)
        if not original_path.exists():
            logger.warning(f"原图不存在: {image_path}")
            return None

        # 检查缓存
        cache_path = self._get_cache_path(image_path, size)
        if cache_path.exists() and not force_regenerate:
            # 检查缓存是否比原图新
            if cache_path.stat().st_mtime >= original_path.stat().st_mtime:
                return cache_path

        # 生成缩略图
        try:
            return self._generate_thumbnail(original_path, cache_path, size)
        except Exception as e:
            logger.error(f"生成缩略图失败: {e}")
            return None

    def _generate_thumbnail(
        self,
        original_path: Path,
        cache_path: Path,
        size: str
    ) -> Path:
        """生成缩略图"""
        target_size = self.THUMBNAIL_SIZES[size]

        # 打开图片
        with Image.open(original_path) as img:
            # 转换为 RGB（处理 RGBA 和其他格式）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # 生成缩略图（保持宽高比）
            img.thumbnail(target_size, Image.Resampling.LANCZOS)

            # 保存
            img.save(cache_path, 'JPEG', quality=85, optimize=True)

        logger.info(f"生成缩略图: {cache_path}")
        return cache_path

    def clear_cache(self, image_path: Optional[str] = None):
        """清理缩略图缓存"""
        if image_path:
            # 清理特定图片的缩略图
            for size in self.THUMBNAIL_SIZES:
                cache_path = self._get_cache_path(image_path, size)
                if cache_path.exists():
                    cache_path.unlink()
                    logger.info(f"清理缩略图缓存: {cache_path}")
        else:
            # 清理所有缩略图
            count = 0
            for cache_file in self.cache_dir.glob("*.jpg"):
                cache_file.unlink()
                count += 1
            logger.info(f"清理所有缩略图缓存: {count} 个文件")
