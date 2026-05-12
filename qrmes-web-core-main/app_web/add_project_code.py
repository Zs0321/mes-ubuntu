#!/usr/bin/env python3
"""
为项目配置添加项目号字段
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

def add_project_code_to_config(config_file: Path, project_code: str = None):
    """为项目配置文件添加项目号"""
    try:
        # 读取配置
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 如果没有提供项目号，使用项目名称作为默认值
        if not project_code:
            project_code = config.get('projectName', config.get('project_name', ''))
        
        # 添加项目号字段
        config['projectCode'] = project_code
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已为 {config_file.name} 添加项目号: {project_code}")
        return True
        
    except Exception as e:
        print(f"✗ 处理 {config_file.name} 失败: {e}")
        return False


def main():
    """主函数"""
    # 获取项目配置目录
    if len(sys.argv) > 1:
        projects_dir = Path(sys.argv[1])
    else:
        projects_dir = resolve_default_projects_dir()
    if not projects_dir.exists():
            projects_dir = Path(__file__).parent.parent / "app" / "files" / "projects"
    
    if not projects_dir.exists():
        print(f"✗ 项目配置目录不存在: {projects_dir}")
        print("用法: python add_project_code.py [项目配置目录路径]")
        return
    
    print(f"📁 项目配置目录: {projects_dir}")
    print("=" * 60)
    
    # 项目号映射（可以根据实际情况修改）
    project_code_mapping = {
        "柳工物流园双12": "LG-WLY-D12",
        "柳工双20": "LG-S20",
        "测试项目": "TEST-001",
        # 添加更多项目映射...
    }
    
    # 处理所有配置文件
    success_count = 0
    total_count = 0
    
    for config_file in projects_dir.glob("*.json"):
        total_count += 1
        
        # 从文件名获取项目名称
        project_name = config_file.stem
        
        # 获取对应的项目号
        project_code = project_code_mapping.get(project_name)
        
        if add_project_code_to_config(config_file, project_code):
            success_count += 1
    
    print("=" * 60)
    print(f"处理完成: {success_count}/{total_count} 个配置文件")
    
    if success_count < total_count:
        print("\n⚠️ 部分文件处理失败，请检查日志")
    else:
        print("\n✓ 所有配置文件处理成功")


if __name__ == '__main__':
    main()
