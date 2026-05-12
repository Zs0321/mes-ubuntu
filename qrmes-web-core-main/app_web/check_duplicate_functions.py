#!/usr/bin/env python3
"""
检查 mesapp.py 中是否有重复的函数名
"""

import re
from collections import Counter

def check_duplicate_functions(filepath):
    """检查文件中是否有重复的函数定义"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找所有函数定义
    pattern = r'^def\s+(\w+)\s*\('
    functions = re.findall(pattern, content, re.MULTILINE)
    
    # 统计函数名出现次数
    function_counts = Counter(functions)
    
    # 查找重复的函数名
    duplicates = {name: count for name, count in function_counts.items() if count > 1}
    
    print(f"总共找到 {len(functions)} 个函数定义")
    print(f"唯一函数名: {len(function_counts)}")
    
    if duplicates:
        print(f"\n❌ 发现 {len(duplicates)} 个重复的函数名:")
        for name, count in duplicates.items():
            print(f"  - {name}: 出现 {count} 次")
            # 查找这些函数的行号
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if re.match(rf'^def\s+{name}\s*\(', line):
                    print(f"    第 {i} 行: {line.strip()}")
        return False
    else:
        print("\n✅ 没有发现重复的函数名")
        return True

if __name__ == "__main__":
    result = check_duplicate_functions("app_web/mesapp.py")
    exit(0 if result else 1)
