#!/usr/bin/env python3
"""
修复配置文件 - 添加 schemaVersion 字段
用于批量更新现有的项目配置文件，确保它们都包含 schemaVersion 字段
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def detect_config_version(config: Dict[str, Any]) -> str:
    """检测配置文件的版本
    
    Returns:
        "2.0" - 新版本（工序在产品类型下）
        "1.0" - 旧版本（工序在顶层）
    """
    schema_version = config.get("schemaVersion", "1.0")
    
    # 如果明确标记了版本，直接返回
    if schema_version in ["2.0", "1.0"]:
        return schema_version
    
    # 否则根据结构判断
    # 新版本特征：productTypes中有processSteps字段
    if "productTypes" in config:
        for product_type in config["productTypes"]:
            if "processSteps" in product_type and len(product_type["processSteps"]) > 0:
                return "2.0"
    
    # 旧版本特征：顶层有processSteps或processAttributes字段
    if "processSteps" in config and len(config.get("processSteps", [])) > 0:
        return "1.0"
    if "processAttributes" in config and len(config.get("processAttributes", [])) > 0:
        return "1.0"
    
    # 默认返回2.0（如果有productTypes但没有工序）
    if "productTypes" in config:
        return "2.0"
    
    return "1.0"


def fix_config_file(config_file: Path) -> bool:
    """修复单个配置文件，添加 schemaVersion 字段
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        bool: 修复成功返回True
    """
    try:
        logger.info(f"处理配置文件: {config_file.name}")
        
        # 读取配置
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 检查是否已有 schemaVersion
        if "schemaVersion" in config:
            logger.info(f"  ✓ 已有 schemaVersion: {config['schemaVersion']}")
            return True
        
        # 检测版本
        detected_version = detect_config_version(config)
        logger.info(f"  检测到版本: {detected_version}")
        
        # 添加 schemaVersion
        config["schemaVersion"] = detected_version
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"  ✓ 已添加 schemaVersion: {detected_version}")
        return True
        
    except Exception as e:
        logger.error(f"  ✗ 处理失败: {e}")
        return False


def main():
    """主函数 - 批量修复配置文件"""
    # 配置文件目录 - 尝试多个可能的路径
    possible_paths = [
        Path("projects"),
        Path("app_web/projects"),
        Path("../projects"),
        Path("QRMES/projects")
    ]
    
    config_dir = None
    for path in possible_paths:
        if path.exists():
            config_dir = path
            logger.info(f"找到配置目录: {config_dir.absolute()}")
            break
    
    if config_dir is None:
        logger.error("配置目录不存在，尝试的路径:")
        for path in possible_paths:
            logger.error(f"  - {path.absolute()}")
        logger.info("\n请在包含 'projects' 目录的位置运行此脚本")
        return
    
    # 查找所有 JSON 配置文件
    config_files = list(config_dir.glob("*.json"))
    
    if not config_files:
        logger.warning("未找到配置文件")
        return
    
    logger.info(f"找到 {len(config_files)} 个配置文件")
    logger.info("=" * 60)
    
    # 处理每个配置文件
    success_count = 0
    failed_count = 0
    
    for config_file in config_files:
        if fix_config_file(config_file):
            success_count += 1
        else:
            failed_count += 1
        logger.info("")
    
    # 输出统计
    logger.info("=" * 60)
    logger.info(f"处理完成:")
    logger.info(f"  成功: {success_count}")
    logger.info(f"  失败: {failed_count}")
    logger.info(f"  总计: {len(config_files)}")


if __name__ == "__main__":
    main()
