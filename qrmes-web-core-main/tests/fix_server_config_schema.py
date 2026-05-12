#!/usr/bin/env python3
"""
通过Web API修复服务器上的配置文件schemaVersion
"""

import sys
import json
from pathlib import Path

# 添加app_web到路径
sys.path.insert(0, str(Path(__file__).parent))

from project_config_manager import ProjectConfigManager

def fix_server_config():
    """修复服务器上的配置"""
    
    # 初始化配置管理器（指向NAS路径）
    # 根据你的实际NAS挂载路径调整
    nas_path = Path("//172.16.30.2/mes/QRMES")
    
    if not nas_path.exists():
        print(f"❌ NAS路径不存在: {nas_path}")
        print("请确保NAS已挂载或使用正确的路径")
        return False
    
    config_manager = ProjectConfigManager(nas_path)
    project_name = "柳工物流园双12"
    
    print(f"正在修复项目: {project_name}")
    print(f"NAS路径: {nas_path}")
    
    # 加载配置
    config = config_manager.get_project_config(project_name)
    
    if not config:
        print(f"❌ 无法加载配置: {project_name}")
        return False
    
    print(f"\n当前配置:")
    print(f"  schemaVersion: {config.get('schemaVersion', 'N/A')}")
    print(f"  productTypes数量: {len(config.get('productTypes', []))}")
    
    # 检查结构
    has_process_in_types = False
    for pt in config.get("productTypes", []):
        if "processSteps" in pt and len(pt.get("processSteps", [])) > 0:
            has_process_in_types = True
            print(f"  产品类型 '{pt['typeName']}' 有 {len(pt['processSteps'])} 个工序")
    
    # 如果是2.0结构但标记为1.0，修复它
    if has_process_in_types and config.get("schemaVersion") != "2.0":
        print("\n✓ 检测到2.0结构，但schemaVersion不正确")
        print("  修复schemaVersion为2.0...")
        
        config["schemaVersion"] = "2.0"
        
        # 保存配置
        success = config_manager.save_project_config(project_name, config)
        
        if success:
            print(f"✓ 已修复服务器配置")
            print(f"  新的 schemaVersion: {config['schemaVersion']}")
            return True
        else:
            print(f"❌ 保存配置失败")
            return False
    else:
        print("\n✓ 配置文件已经正确")
        return True

if __name__ == "__main__":
    fix_server_config()
