#!/usr/bin/env python3
"""
为项目配置的产品类型添加 modelNumber 字段
"""

import json
import os
import sys
from pathlib import Path


def resolve_default_projects_dir() -> Path:
    """????????????????????????"""
    env_data_dir = (os.getenv("MESAPP_DATA_DIR") or os.getenv("DATA_DIR") or "").strip()
    if env_data_dir:
        return Path(env_data_dir) / "projects"

    try:
        from qrmes_shared_core.config import config

        configured = str(config.nas_local_base_path or "").strip()
        if configured:
            return Path(configured) / "projects"
    except Exception:
        pass

    return Path(__file__).resolve().parent.parent / "QRMES" / "projects"

def add_model_number_to_config(config_file: Path):
    """为项目配置添加产品型号"""
    try:
        # 读取配置
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        modified = False
        
        # 检查是否有 productTypes
        if 'productTypes' not in config:
            print(f"⚠ {config_file.name}: 没有 productTypes 字段")
            return False
        
        # 为每个产品类型添加 modelNumber
        for pt in config['productTypes']:
            type_name = pt.get('typeName', '未知')
            
            # 如果已经有 modelNumber，跳过
            if 'modelNumber' in pt and pt['modelNumber']:
                print(f"  {type_name}: 已有型号 {pt['modelNumber']}")
                continue
            
            # 根据产品类型名称生成默认型号
            # 这里需要根据实际情况修改
            default_model = generate_default_model_number(type_name, config.get('projectName', ''))
            
            pt['modelNumber'] = default_model
            modified = True
            print(f"  {type_name}: 添加型号 {default_model}")
        
        if modified:
            # 保存配置
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            print(f"✓ {config_file.name}: 已更新")
            return True
        else:
            print(f"  {config_file.name}: 无需更新")
            return False
        
    except Exception as e:
        print(f"✗ {config_file.name}: 处理失败 - {e}")
        return False


def generate_default_model_number(type_name: str, project_name: str) -> str:
    """
    生成默认的产品型号
    
    这里提供一个简单的生成规则，实际使用时需要根据业务规则修改
    """
    # 产品类型映射表（需要根据实际情况完善）
    type_mapping = {
        '油泵电机': 'TZ180111',
        '电机': 'MOTOR-001',
        '电机控制器': 'MCU-001',
        '控制器': 'CTRL-001',
    }
    
    # 如果有映射，使用映射的型号
    if type_name in type_mapping:
        return type_mapping[type_name]
    
    # 否则生成一个默认型号
    # 格式: 项目简称-产品类型简称
    project_abbr = ''.join([c for c in project_name if c.isupper() or c.isdigit()])[:4]
    type_abbr = ''.join([c for c in type_name if c.isupper() or c.isdigit()])[:4]
    
    if not project_abbr:
        project_abbr = 'PROJ'
    if not type_abbr:
        type_abbr = 'TYPE'
    
    return f"{project_abbr}-{type_abbr}-001"


def main():
    """主函数"""
    # 获取项目配置目录
    if len(sys.argv) > 1:
        projects_dir = Path(sys.argv[1])
    else:
        projects_dir = resolve_default_projects_dir()
    if not projects_dir.exists():
            projects_dir = Path(__file__).parent / "projects"
    
    if not projects_dir.exists():
        print(f"✗ 项目配置目录不存在: {projects_dir}")
        print("用法: python add_model_number.py [项目配置目录路径]")
        return
    
    print(f"📁 项目配置目录: {projects_dir}")
    print("=" * 60)
    
    # 处理所有配置文件
    success_count = 0
    total_count = 0
    
    for config_file in sorted(projects_dir.glob("*.json")):
        total_count += 1
        print(f"\n处理: {config_file.name}")
        
        if add_model_number_to_config(config_file):
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"处理完成: {success_count}/{total_count} 个配置文件已更新")
    
    if success_count < total_count:
        print("\n⚠️ 部分文件未更新，请检查日志")
    else:
        print("\n✓ 所有配置文件处理完成")
    
    print("\n提示:")
    print("  1. 请检查生成的型号是否正确")
    print("  2. 如需修改，请编辑配置文件中的 modelNumber 字段")
    print("  3. 重启 mesapp.py 服务使更改生效")


if __name__ == '__main__':
    main()
