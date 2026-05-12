#!/usr/bin/env python3
"""
权限配置文件生成工具

从数据库读取用户权限，生成 JSON 配置文件供移动端 WebDAV 访问
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qrmes_shared_core.user_management_service import UserManagementService
from qrmes_shared_core.permission_service import PermissionService


class PermissionsFileGenerator:
    """权限配置文件生成器"""
    
    def __init__(self, output_dir: str = "/volume2/MES/files/config"):
        """
        初始化生成器
        
        Args:
            output_dir: 输出目录路径
        """
        self.output_dir = Path(output_dir)
        self.user_service = UserManagementService()
        self.permission_service = PermissionService()
        
    def generate_permissions_file(self) -> dict:
        """
        生成权限配置文件内容
        
        Returns:
            dict: 权限配置字典
        """
        print("正在从数据库读取用户权限...")
        
        # 获取所有用户
        users = self.user_service.get_all_users()
        
        if not users:
            print("警告: 数据库中没有用户")
            return self._create_empty_config()
        
        # 构建用户权限配置
        users_config = {}
        for user in users:
            username = user['username']
            
            # 获取用户权限
            permissions = self.permission_service.get_user_permissions(username)
            
            if permissions:
                users_config[username] = {
                    "role": user['role'],
                    "display_name": user.get('display_name', username),
                    "permissions": {
                        "can_modify_records": permissions.get('can_modify_records', False),
                        "can_delete_records": permissions.get('can_delete_records', False),
                        "can_manage_users": permissions.get('can_manage_users', False),
                        "can_access_all_projects": permissions.get('can_access_all_projects', False),
                        "can_record_material": True,  # 所有用户都可以记录物料
                        "can_record_process": True    # 所有用户都可以记录工序
                    },
                    "allowed_projects": ["*"] if permissions.get('can_access_all_projects') else []
                }
                
                print(f"  ✓ 添加用户: {username} (角色: {user['role']})")
        
        # 构建完整配置
        config = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "users": users_config
        }
        
        print(f"\n成功生成 {len(users_config)} 个用户的权限配置")
        return config
    
    def _create_empty_config(self) -> dict:
        """创建空配置"""
        return {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "users": {}
        }
    
    def save_to_file(self, config: dict, filename: str = "users.json") -> bool:
        """
        保存配置到文件
        
        Args:
            config: 配置字典
            filename: 文件名
            
        Returns:
            bool: 是否成功
        """
        try:
            # 确保输出目录存在
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存文件
            output_file = self.output_dir / filename
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ 权限配置文件已保存到: {output_file}")
            print(f"  文件大小: {output_file.stat().st_size} 字节")
            
            # 设置文件权限（可读可写）
            os.chmod(output_file, 0o666)
            
            return True
        except Exception as e:
            print(f"\n✗ 保存文件失败: {e}")
            return False
    
    def generate_policy_file(self, filename: str = "permissions_policy.json") -> bool:
        """
        生成权限策略配置文件
        
        Args:
            filename: 文件名
            
        Returns:
            bool: 是否成功
        """
        policy = {
            "version": "1.0",
            "roles": {
                "admin": {
                    "description": "管理员",
                    "default_permissions": {
                        "can_modify_records": True,
                        "can_delete_records": True,
                        "can_manage_users": True,
                        "can_access_all_projects": True,
                        "can_record_material": True,
                        "can_record_process": True
                    }
                },
                "user": {
                    "description": "普通用户",
                    "default_permissions": {
                        "can_modify_records": False,
                        "can_delete_records": False,
                        "can_manage_users": False,
                        "can_access_all_projects": False,
                        "can_record_material": True,
                        "can_record_process": True
                    }
                }
            },
            "cache_ttl_seconds": 300,
            "file_update_interval_seconds": 60
        }
        
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_file = self.output_dir / filename
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(policy, f, ensure_ascii=False, indent=2)
            
            print(f"✓ 权限策略文件已保存到: {output_file}")
            os.chmod(output_file, 0o666)
            
            return True
        except Exception as e:
            print(f"✗ 保存策略文件失败: {e}")
            return False


def main():
    """主函数"""
    print("=" * 60)
    print("权限配置文件生成工具")
    print("=" * 60)
    print()
    
    # 检查输出目录参数
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "/volume2/MES/files/config"
    
    print(f"输出目录: {output_dir}")
    print()
    
    # 创建生成器
    generator = PermissionsFileGenerator(output_dir)
    
    # 生成权限配置文件
    config = generator.generate_permissions_file()
    success1 = generator.save_to_file(config)
    
    print()
    
    # 生成权限策略文件
    success2 = generator.generate_policy_file()
    
    print()
    print("=" * 60)
    
    if success1 and success2:
        print("✓ 所有文件生成成功！")
        print()
        print("移动端 WebDAV 用户现在可以通过下载这些文件获取权限配置")
        print()
        print("文件路径:")
        print(f"  - {output_dir}/users.json")
        print(f"  - {output_dir}/permissions_policy.json")
        return 0
    else:
        print("✗ 部分文件生成失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
