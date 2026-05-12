#!/usr/bin/env python3
"""
整理app_web文件夹
将测试文件、文档、临时脚本移到archive文件夹
只保留运行必需的文件
"""

import os
import shutil
from pathlib import Path

# 运行必需的文件和文件夹
REQUIRED_FILES = {
    # 核心Python文件
    'mesapp.py',
    'auth.py',
    'config.py',
    'h2_api.py',
    'csv_monitor.py',
    'smb_client.py',
    'webdav_client_v2.py',
    'webdav_client.py',
    'enhanced_logger.py',
    
    # API文件
    'photo_api.py',
    'process_config_api.py',
    'permission_api.py',
    
    # 服务文件
    'user_management_service.py',
    'permission_service.py',
    'synology_auth_client.py',
    'data_access_layer.py',
    'database_schema.py',
    'project_config_manager.py',
    'config_history_manager.py',
    'error_handler.py',
    'security_validator.py',
    
    # 配置文件
    'webdav_config.json',
    'webdav_config.json.example',
    'requirements.txt',
    
    # 启动脚本
    'start_simple.sh',
    
    # 说明文件
    'SIMPLIFIED_SETUP.md',
    '使用说明.md',
}

REQUIRED_DIRS = {
    'templates',
    'static',
    'deployment',
    'docs',
    '__pycache__',
    'cache',
    'logs',
    'record',
}

def organize_files():
    """整理文件"""
    app_web_dir = Path(__file__).parent
    archive_dir = app_web_dir / 'archive'
    
    print("=" * 60)
    print("整理 app_web 文件夹")
    print("=" * 60)
    
    # 创建archive目录
    archive_dir.mkdir(exist_ok=True)
    print(f"\n✓ 创建归档目录: {archive_dir}")
    
    # 创建子目录
    (archive_dir / 'test_files').mkdir(exist_ok=True)
    (archive_dir / 'docs').mkdir(exist_ok=True)
    (archive_dir / 'scripts').mkdir(exist_ok=True)
    (archive_dir / 'demo_files').mkdir(exist_ok=True)
    (archive_dir / 'backup_files').mkdir(exist_ok=True)
    
    moved_count = 0
    kept_count = 0
    
    # 遍历所有文件
    for item in app_web_dir.iterdir():
        # 跳过archive目录本身和此脚本
        if item.name == 'archive' or item.name == 'organize_files.py':
            continue
        
        # 保留必需的目录
        if item.is_dir() and item.name in REQUIRED_DIRS:
            kept_count += 1
            continue
        
        # 保留必需的文件
        if item.is_file() and item.name in REQUIRED_FILES:
            kept_count += 1
            continue
        
        # 移动其他文件
        if item.is_file():
            # 确定目标目录
            if item.name.startswith('test_'):
                target_dir = archive_dir / 'test_files'
            elif item.name.endswith('.md') or item.name.endswith('.txt'):
                target_dir = archive_dir / 'docs'
            elif item.name.endswith('.sh') or item.name.endswith('.ps1') or item.name.endswith('.py'):
                target_dir = archive_dir / 'scripts'
            elif 'demo' in item.name.lower() or 'backup' in item.name.lower():
                target_dir = archive_dir / 'backup_files'
            else:
                target_dir = archive_dir / 'demo_files'
            
            # 移动文件
            try:
                target_path = target_dir / item.name
                if target_path.exists():
                    print(f"  跳过 (已存在): {item.name}")
                else:
                    shutil.move(str(item), str(target_path))
                    print(f"  移动: {item.name} -> {target_dir.name}/")
                    moved_count += 1
            except Exception as e:
                print(f"  ✗ 移动失败: {item.name} - {e}")
    
    print("\n" + "=" * 60)
    print(f"整理完成")
    print("=" * 60)
    print(f"保留文件/目录: {kept_count}")
    print(f"移动文件: {moved_count}")
    print(f"\n归档位置: {archive_dir}")
    print("\n保留的核心文件:")
    print("-" * 60)
    for f in sorted(REQUIRED_FILES):
        if (app_web_dir / f).exists():
            print(f"  ✓ {f}")
    
    print("\n保留的目录:")
    print("-" * 60)
    for d in sorted(REQUIRED_DIRS):
        if (app_web_dir / d).exists():
            print(f"  ✓ {d}/")
    
    # 创建README
    readme_content = """# Archive 归档目录

这个目录包含了从 app_web 主目录移动过来的非必需文件。

## 目录结构

- **test_files/** - 所有测试文件
- **docs/** - 文档和说明文件
- **scripts/** - 临时脚本和工具
- **demo_files/** - 演示和示例文件
- **backup_files/** - 备份文件

## 说明

这些文件已被移到归档目录，以保持主目录的整洁。
如果需要这些文件，可以从这里找到。

整理日期: """ + str(Path.ctime(archive_dir))
    
    with open(archive_dir / 'README.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print("\n✓ 已创建归档说明文件: archive/README.md")

if __name__ == '__main__':
    try:
        organize_files()
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
