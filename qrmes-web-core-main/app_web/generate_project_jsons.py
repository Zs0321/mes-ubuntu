#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目JSON文件生成脚本
根据projects.json中的项目名称和Excel文件中的数据，为每个项目生成对应的JSON配置文件
"""

import json
import pandas as pd
import os
from datetime import datetime
import time
import re

def load_projects_list():
    """加载projects.json中的项目列表"""
    try:
        with open('projects.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('projects', [])
    except Exception as e:
        print(f"读取projects.json失败: {e}")
        return []

def load_project_codes():
    """从预置基础资料3文件中加载项目号映射"""
    try:
        df = pd.read_excel('预置基础资料3_2025102023294506_128558.xlsx')
        # 创建项目名称到项目号的映射
        project_codes = {}
        for _, row in df.iterrows():
            project_name = str(row['项目名称']).strip()
            project_code = str(row['项目号']).strip()
            if project_name and project_code and project_name != 'nan' and project_code != 'nan':
                project_codes[project_name] = project_code
        return project_codes
    except Exception as e:
        print(f"读取项目号文件失败: {e}")
        return {}

def load_product_info():
    """从项目文件中加载产品信息"""
    try:
        df = pd.read_excel('项目_2025102023291675_128558.xlsx')
        # 按项目名称分组产品信息
        product_info = {}
        for _, row in df.iterrows():
            project_name = str(row['项目名称']).strip()
            product_type = str(row['产品类型']).strip()
            # 注意：不再读取Excel中的产品型号，产品型号将基于项目号生成
            
            if project_name and product_type:
                if project_name not in product_info:
                    product_info[project_name] = []
                
                # 检查是否已存在相同的产品类型
                existing_product = None
                for product in product_info[project_name]:
                    if product['typeName'] == product_type:
                        existing_product = product
                        break
                
                if not existing_product:
                    # 添加新的产品类型（不包含modelNumber，稍后基于项目号生成）
                    product_info[project_name].append({
                        'typeName': product_type,
                        'materials': [],
                        'processSteps': []
                    })
        
        return product_info
    except Exception as e:
        print(f"读取产品信息文件失败: {e}")
        return {}

def generate_product_model_number(project_code, product_index):
    """基于项目号和产品序号生成产品型号"""
    return f"{project_code}-{product_index:03d}"

def sanitize_filename(filename):
    """清理文件名，移除不合法字符"""
    # 移除或替换不合法的文件名字符
    illegal_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(illegal_chars, '_', filename)
    # 移除多余的空格和点
    sanitized = sanitized.strip('. ')
    return sanitized

def generate_project_json(project_name, project_code, product_types):
    """生成单个项目的JSON配置"""
    current_time = datetime.now()
    timestamp = int(time.time() * 1000)
    
    project_config = {
        "projectName": project_name,
        "projectCode": project_code,
        "schemaVersion": "2.1",
        "version": 1,
        "lastModified": timestamp,
        "createdAt": current_time.isoformat(),
        "updatedAt": current_time.isoformat(),
        "createdBy": "system",
        "description": f"{project_name}项目配置",
        "productTypes": product_types,
        "processSteps": [],
        "metadata": {
            "configFormat": "v2.0",
            "supportedFeatures": [
                "productTypes",
                "processSteps",
                "versionControl"
            ],
            "lastBackup": None,
            "totalVersions": 1
        },
        "configVersion": 2
    }
    
    return project_config

def main():
    """主函数"""
    print("开始生成项目JSON文件...")
    
    # 确保projects目录存在
    projects_dir = 'projects'
    if not os.path.exists(projects_dir):
        os.makedirs(projects_dir)
        print(f"创建目录: {projects_dir}")
    
    # 加载数据
    print("加载项目列表...")
    projects = load_projects_list()
    print(f"找到 {len(projects)} 个项目")
    
    print("加载项目号映射...")
    project_codes = load_project_codes()
    print(f"找到 {len(project_codes)} 个项目号映射")
    
    print("加载产品信息...")
    product_info = load_product_info()
    print(f"找到 {len(product_info)} 个项目的产品信息")
    
    # 生成JSON文件
    created_count = 0
    skipped_count = 0
    
    for project_name in projects:
        try:
            # 获取项目号
            project_code = project_codes.get(project_name, "UNKNOWN")
            
            # 使用智能匹配查找产品信息
            matched_project_name = find_matching_project_name(project_name, product_info.keys())
            if matched_project_name:
                raw_product_types = product_info[matched_project_name]
                # 为每个产品类型生成基于项目号的产品型号
                product_types = []
                for index, product_type in enumerate(raw_product_types, 1):
                    product_with_model = product_type.copy()
                    product_with_model['modelNumber'] = generate_product_model_number(project_code, index)
                    product_types.append(product_with_model)
                print(f"项目 '{project_name}' 匹配到产品信息: '{matched_project_name}' (产品类型: {len(product_types)})")
            else:
                product_types = []
                print(f"项目 '{project_name}' 未找到匹配的产品信息")
            
            # 生成JSON配置
            project_config = generate_project_json(project_name, project_code, product_types)
            
            # 生成文件名
            safe_filename = sanitize_filename(project_name)
            json_filename = f"{safe_filename}.json"
            json_filepath = os.path.join(projects_dir, json_filename)
            
            # 检查文件是否已存在
            if os.path.exists(json_filepath):
                print(f"跳过已存在的文件: {json_filename}")
                skipped_count += 1
                continue
            
            # 写入JSON文件
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(project_config, f, ensure_ascii=False, indent=2)
            
            print(f"创建: {json_filename} (项目号: {project_code}, 产品类型: {len(product_types)})")
            created_count += 1
            
        except Exception as e:
            print(f"处理项目 '{project_name}' 时出错: {e}")
            continue
    
    print(f"\n生成完成!")
    print(f"新创建文件: {created_count}")
    print(f"跳过已存在: {skipped_count}")
    print(f"总项目数: {len(projects)}")

def normalize_project_name(name):
    """标准化项目名称，用于匹配"""
    if not name:
        return ""
    
    # 转换为小写并去除空格
    normalized = name.lower().replace(" ", "").replace("　", "")
    
    # 统一重量单位表示
    normalized = normalized.replace("吨", "t").replace("T", "t")
    
    # 移除"智能"等修饰词
    normalized = normalized.replace("智能", "")
    
    return normalized

def find_matching_project_name(target_name, product_info_keys):
    """在产品信息中查找匹配的项目名称"""
    target_normalized = normalize_project_name(target_name)
    
    # 首先尝试精确匹配
    if target_name in product_info_keys:
        return target_name
    
    # 然后尝试标准化匹配
    for key in product_info_keys:
        key_normalized = normalize_project_name(key)
        if target_normalized == key_normalized:
            return key
    
    # 最后尝试部分匹配（包含关系）
    for key in product_info_keys:
        key_normalized = normalize_project_name(key)
        # 检查是否有足够的相似性
        if (target_normalized in key_normalized or key_normalized in target_normalized) and len(target_normalized) > 3:
            return key
    
    return None

if __name__ == "__main__":
    main()