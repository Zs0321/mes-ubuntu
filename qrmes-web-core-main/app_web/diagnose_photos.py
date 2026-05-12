#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
照片诊断工具
检查并报告损坏或无法识别的图片文件
"""

import os
import sys
from pathlib import Path
from PIL import Image
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_image(image_path: Path) -> dict:
    """
    检查单个图片文件
    
    Returns:
        dict: {
            'path': str,
            'valid': bool,
            'error': str or None,
            'format': str or None,
            'size': tuple or None
        }
    """
    result = {
        'path': str(image_path),
        'valid': False,
        'error': None,
        'format': None,
        'size': None,
        'file_size': image_path.stat().st_size if image_path.exists() else 0
    }
    
    try:
        with Image.open(image_path) as img:
            result['valid'] = True
            result['format'] = img.format
            result['size'] = img.size
            result['mode'] = img.mode
    except Exception as e:
        result['error'] = str(e)
    
    return result

def scan_directory(base_dir: str, extensions: list = ['.jpg', '.jpeg', '.png']) -> dict:
    """
    扫描目录中的所有图片
    
    Returns:
        dict: {
            'total': int,
            'valid': int,
            'invalid': int,
            'invalid_files': list
        }
    """
    base_path = Path(base_dir)
    
    if not base_path.exists():
        logger.error(f"目录不存在: {base_dir}")
        return None
    
    logger.info(f"开始扫描目录: {base_dir}")
    
    stats = {
        'total': 0,
        'valid': 0,
        'invalid': 0,
        'invalid_files': [],
        'zero_size': 0,
        'zero_size_files': []
    }
    
    # 递归扫描所有图片文件
    for ext in extensions:
        for image_path in base_path.rglob(f'*{ext}'):
            if not image_path.is_file():
                continue
            
            stats['total'] += 1
            
            # 检查文件大小
            if image_path.stat().st_size == 0:
                stats['zero_size'] += 1
                stats['zero_size_files'].append(str(image_path))
                logger.warning(f"空文件: {image_path}")
                continue
            
            # 检查图片
            result = check_image(image_path)
            
            if result['valid']:
                stats['valid'] += 1
                if stats['total'] % 100 == 0:
                    logger.info(f"已检查: {stats['total']} 个文件")
            else:
                stats['invalid'] += 1
                stats['invalid_files'].append(result)
                logger.error(f"损坏的图片: {image_path} - {result['error']}")
    
    return stats

def generate_report(stats: dict, output_file: str = 'photo_diagnosis_report.txt'):
    """生成诊断报告"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("照片诊断报告\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"总文件数: {stats['total']}\n")
            f.write(f"有效文件: {stats['valid']}\n")
            f.write(f"损坏文件: {stats['invalid']}\n")
            f.write(f"空文件: {stats['zero_size']}\n")
            f.write(f"成功率: {stats['valid'] / stats['total'] * 100:.2f}%\n\n")
            
            if stats['zero_size_files']:
                f.write("-" * 80 + "\n")
                f.write("空文件列表:\n")
                f.write("-" * 80 + "\n")
                for file_path in stats['zero_size_files']:
                    f.write(f"{file_path}\n")
                f.write("\n")
            
            if stats['invalid_files']:
                f.write("-" * 80 + "\n")
                f.write("损坏文件详情:\n")
                f.write("-" * 80 + "\n")
                for file_info in stats['invalid_files']:
                    f.write(f"\n文件: {file_info['path']}\n")
                    f.write(f"  大小: {file_info['file_size']} bytes\n")
                    f.write(f"  错误: {file_info['error']}\n")
        
        logger.info(f"报告已生成: {output_file}")
        
    except Exception as e:
        logger.error(f"生成报告失败: {e}")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python diagnose_photos.py <图片目录路径>")
        print("示例: python diagnose_photos.py /volume2/MES/QRMES/picture")
        sys.exit(1)
    
    base_dir = sys.argv[1]
    
    logger.info("开始照片诊断...")
    stats = scan_directory(base_dir)
    
    if stats:
        logger.info("\n" + "=" * 80)
        logger.info("诊断完成")
        logger.info("=" * 80)
        logger.info(f"总文件数: {stats['total']}")
        logger.info(f"有效文件: {stats['valid']}")
        logger.info(f"损坏文件: {stats['invalid']}")
        logger.info(f"空文件: {stats['zero_size']}")
        logger.info(f"成功率: {stats['valid'] / stats['total'] * 100:.2f}%")
        
        # 生成报告
        generate_report(stats)
        
        if stats['invalid'] > 0 or stats['zero_size'] > 0:
            logger.warning(f"\n发现 {stats['invalid'] + stats['zero_size']} 个问题文件，请查看报告文件")
            logger.warning("建议操作:")
            logger.warning("1. 删除空文件和损坏文件")
            logger.warning("2. 重新上传这些照片")
            logger.warning("3. 清空照片缓存黑名单: 在服务器上删除 cache/photos/failed_images.txt")

if __name__ == '__main__':
    main()
