#!/usr/bin/env python3
"""
修复柳工物流园双12配置文件的schemaVersion
将schemaVersion从"1.0"改为"2.0"
"""

import json
from pathlib import Path

def fix_config():
    """修复配置文件"""
    config_file = Path("柳工物流园双12.json")
    
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_file}")
        return False
    
    # 读取配置
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print(f"当前 schemaVersion: {config.get('schemaVersion', 'N/A')}")
    
    # 检查结构
    has_product_types = "productTypes" in config
    has_process_in_types = False
    
    if has_product_types:
        for pt in config["productTypes"]:
            if "processSteps" in pt and len(pt.get("processSteps", [])) > 0:
                has_process_in_types = True
                break
    
    print(f"有productTypes: {has_product_types}")
    print(f"productTypes中有processSteps: {has_process_in_types}")
    
    # 如果是2.0结构但标记为1.0，修复它
    if has_process_in_types and config.get("schemaVersion") != "2.0":
        print("\n✓ 检测到2.0结构，但schemaVersion不正确")
        print("  修复schemaVersion为2.0...")
        
        config["schemaVersion"] = "2.0"
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已修复配置文件: {config_file}")
        print(f"  新的 schemaVersion: {config['schemaVersion']}")
        return True
    else:
        print("\n✓ 配置文件已经正确")
        return True

if __name__ == "__main__":
    fix_config()
