"""
修复时区显示问题
将UTC时间戳转换为中国时区（GMT+8）显示
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 中国时区 GMT+8
CHINA_TZ = timezone(timedelta(hours=8))

def format_timestamp_to_china_time(timestamp_ms: int) -> str:
    """将UTC毫秒时间戳转换为中国时区时间字符串"""
    if not timestamp_ms:
        return ""
    
    # 转换为秒
    timestamp_sec = timestamp_ms / 1000
    
    # 创建UTC时间
    utc_time = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
    
    # 转换为中国时区
    china_time = utc_time.astimezone(CHINA_TZ)
    
    # 格式化为字符串
    return china_time.strftime("%Y-%m-%d %H:%M:%S")


def test_timezone_conversion():
    """测试时区转换"""
    print("=" * 60)
    print("时区转换测试")
    print("=" * 60)
    
    # 测试案例：2025-10-21 10:28:08 (中国时间)
    # 对应的UTC时间应该是 2025-10-21 02:28:08
    # 存储的时间戳应该是UTC时间的毫秒数
    
    # 模拟数据库中的UTC时间戳（18:28:08 UTC = 10:28:08 GMT+8 - 8小时）
    # 实际上数据库存的是 18:28:08，说明存储时就错了
    
    test_cases = [
        ("2025-10-21 10:28:08", "中国本地时间"),
        ("2025-10-21 18:28:08", "数据库UTC时间（错误）"),
    ]
    
    for time_str, desc in test_cases:
        # 解析为datetime对象（假设是中国时间）
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        
        # 设置为中国时区
        china_dt = dt.replace(tzinfo=CHINA_TZ)
        
        # 转换为UTC
        utc_dt = china_dt.astimezone(timezone.utc)
        
        # 转换为时间戳（毫秒）
        timestamp_ms = int(utc_dt.timestamp() * 1000)
        
        # 反向转换测试
        converted = format_timestamp_to_china_time(timestamp_ms)
        
        print(f"\n{desc}:")
        print(f"  输入: {time_str}")
        print(f"  中国时区: {china_dt}")
        print(f"  UTC时区: {utc_dt}")
        print(f"  时间戳(ms): {timestamp_ms}")
        print(f"  转换回来: {converted}")


def check_database_records():
    """检查数据库中的时间记录"""
    db_path = Path("/volume2/MES/QRMES/record/product_records.db")
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    print("\n" + "=" * 60)
    print("数据库时间记录检查")
    print("=" * 60)
    
    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT product_serial, project_name, operator, scan_time
                FROM product_records
                ORDER BY scan_time DESC
                LIMIT 10
            """)
            
            records = cursor.fetchall()
            
            if not records:
                print("数据库中没有记录")
                return
            
            print(f"\n找到 {len(records)} 条最新记录:\n")
            
            for row in records:
                record = dict(row)
                timestamp_ms = record['scan_time']
                
                # UTC时间
                utc_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                
                # 中国时间
                china_time = format_timestamp_to_china_time(timestamp_ms)
                
                print(f"产品序列号: {record['product_serial']}")
                print(f"  项目: {record['project_name']}")
                print(f"  操作员: {record['operator']}")
                print(f"  时间戳: {timestamp_ms}")
                print(f"  UTC时间: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  中国时间: {china_time}")
                print()
                
    except Exception as e:
        print(f"❌ 查询失败: {e}")


def add_timezone_helper_to_api():
    """生成API时间转换辅助代码"""
    print("\n" + "=" * 60)
    print("API时间转换辅助代码")
    print("=" * 60)
    
    code = '''
# 在 h2_api.py 中添加以下代码

from datetime import datetime, timezone, timedelta

# 中国时区 GMT+8
CHINA_TZ = timezone(timedelta(hours=8))

def format_timestamp_to_china_time(timestamp_ms: int) -> str:
    """将UTC毫秒时间戳转换为中国时区时间字符串"""
    if not timestamp_ms:
        return ""
    
    timestamp_sec = timestamp_ms / 1000
    utc_time = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
    china_time = utc_time.astimezone(CHINA_TZ)
    return china_time.strftime("%Y-%m-%d %H:%M:%S")

# 在返回记录时添加格式化的时间字段
def get_record(self, product_serial: str) -> Optional[Dict]:
    """查询单条记录"""
    try:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM product_records WHERE product_serial = ?",
                (product_serial,)
            )
            row = cursor.fetchone()
            if row:
                record = dict(row)
                # 添加格式化的中国时间
                record['scan_time_formatted'] = format_timestamp_to_china_time(record['scan_time'])
                return record
            return None
    except Exception as e:
        logger.error(f"查询失败: {e}")
        return None
'''
    
    print(code)


if __name__ == "__main__":
    print("🕐 时区显示问题诊断工具\n")
    
    # 1. 测试时区转换
    test_timezone_conversion()
    
    # 2. 检查数据库记录
    check_database_records()
    
    # 3. 生成修复代码
    add_timezone_helper_to_api()
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)
    print("\n建议修复方案:")
    print("1. 在 h2_api.py 中添加时区转换函数")
    print("2. 在返回记录时添加 scan_time_formatted 字段")
    print("3. 前端显示时使用 scan_time_formatted 而不是 scan_time")
    print("4. 或者在前端JavaScript中进行时区转换")
