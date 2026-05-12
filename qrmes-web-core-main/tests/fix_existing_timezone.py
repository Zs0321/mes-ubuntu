#!/usr/bin/env python3
"""
修复现有H2数据库中的时区问题
将错误的UTC时间戳修正为正确的中国时区时间戳
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHINA_TZ = timezone(timedelta(hours=8))
DB_PATH = "/volume2/MES/QRMES/record/product_records.db"


def analyze_timezone_issue():
    """分析时区问题"""
    print("\n" + "="*60)
    print(" 时区问题分析")
    print("="*60)
    
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT product_serial, scan_time, operator, project_name
            FROM product_records 
            ORDER BY scan_time DESC 
            LIMIT 5
        """)
        
        print("\n最新5条记录的时间分析：\n")
        
        for row in cursor.fetchall():
            timestamp_ms = row['scan_time']
            
            # 当前解释（错误）：直接作为UTC时间戳
            utc_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            china_time_wrong = utc_time.astimezone(CHINA_TZ)
            
            # 正确解释：时间戳已经是中国时区的，需要减去8小时
            correct_timestamp = timestamp_ms - (8 * 3600 * 1000)
            correct_utc = datetime.fromtimestamp(correct_timestamp / 1000, tz=timezone.utc)
            correct_china = correct_utc.astimezone(CHINA_TZ)
            
            print(f"产品: {row['product_serial']}")
            print(f"  时间戳: {timestamp_ms}")
            print(f"  当前显示（错误）: {china_time_wrong.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  应该显示（正确）: {correct_china.strftime('%Y-%m-%d %H:%M:%S')}")
            print()


def fix_timezone_in_database(dry_run=True):
    """修复数据库中的时区问题"""
    print("\n" + "="*60)
    print(f" 时区修复 {'（预览模式）' if dry_run else '（执行模式）'}")
    print("="*60)
    
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        
        # 获取所有记录
        cursor.execute("SELECT product_serial, scan_time FROM product_records")
        records = cursor.fetchall()
        
        print(f"\n找到 {len(records)} 条记录需要修复\n")
        
        fixed_count = 0
        
        for product_serial, scan_time in records:
            # 修正时间戳：减去8小时（28800000毫秒）
            correct_timestamp = scan_time - (8 * 3600 * 1000)
            
            if not dry_run:
                cursor.execute("""
                    UPDATE product_records 
                    SET scan_time = ?, updated_at = ?
                    WHERE product_serial = ?
                """, (correct_timestamp, int(datetime.now().timestamp() * 1000), product_serial))
            
            fixed_count += 1
            
            if fixed_count <= 5:  # 只显示前5条
                old_time = datetime.fromtimestamp(scan_time / 1000, tz=timezone.utc).astimezone(CHINA_TZ)
                new_time = datetime.fromtimestamp(correct_timestamp / 1000, tz=timezone.utc).astimezone(CHINA_TZ)
                print(f"  {product_serial}:")
                print(f"    修正前: {old_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"    修正后: {new_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not dry_run:
            conn.commit()
            print(f"\n✓ 已修复 {fixed_count} 条记录")
        else:
            print(f"\n预览完成，共 {fixed_count} 条记录需要修复")
            print("\n要执行修复，请运行: python3 fix_existing_timezone.py --fix")


def verify_fix():
    """验证修复结果"""
    print("\n" + "="*60)
    print(" 验证修复结果")
    print("="*60)
    
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT product_serial, scan_time, operator
            FROM product_records 
            ORDER BY scan_time DESC 
            LIMIT 5
        """)
        
        print("\n最新5条记录：\n")
        
        for row in cursor.fetchall():
            timestamp_ms = row['scan_time']
            utc_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            china_time = utc_time.astimezone(CHINA_TZ)
            
            print(f"产品: {row['product_serial']}")
            print(f"  操作员: {row['operator']}")
            print(f"  时间戳: {timestamp_ms}")
            print(f"  显示时间: {china_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print()


def main():
    import sys
    
    print("="*60)
    print(" H2数据库时区修复工具")
    print("="*60)
    print(f" 数据库: {DB_PATH}")
    print(f" 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查数据库是否存在
    if not Path(DB_PATH).exists():
        print(f"\n✗ 数据库文件不存在: {DB_PATH}")
        return 1
    
    # 分析问题
    analyze_timezone_issue()
    
    # 执行修复
    if '--fix' in sys.argv:
        confirm = input("\n⚠️  确认要修复数据库吗？(yes/no): ")
        if confirm.lower() == 'yes':
            fix_timezone_in_database(dry_run=False)
            verify_fix()
        else:
            print("取消修复")
    else:
        fix_timezone_in_database(dry_run=True)
    
    return 0


if __name__ == '__main__':
    exit(main())
