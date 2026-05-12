# 照片缓存系统使用指南

## 概述

照片缓存系统通过生成缩略图和压缩图来优化 Web 端的照片加载性能，同时提供完善的降级机制。

## 缓存位置

```
app_web/
├── cache/
│   └── photos/
│       ├── thumbnails/      # 缩略图 (300x300)
│       ├── compressed/      # 压缩图 (最大宽度1200px)
│       └── failed_images.txt # 失败图片黑名单
```

**重要**: 缓存文件完全独立，不会影响原始照片（位于 `<DATA_DIR>/picture/`）

## 工作原理

### 1. 正常流程
```
用户请求照片 → 检查缓存 → 缓存存在 → 返回缓存
                    ↓
                缓存不存在 → 生成缓存 → 返回缓存
```

### 2. 降级流程（新增）
```
用户请求照片 → 检查黑名单 → 在黑名单中 → 直接返回原图
                    ↓
                不在黑名单 → 尝试生成缓存
                    ↓
                生成失败 → 记录到黑名单 → 返回原图
```

## 失败图片处理

### 为什么会失败？

1. **文件损坏** - 上传过程中断或存储错误
2. **格式错误** - 文件扩展名是 .jpg 但实际不是有效图片
3. **空文件** - 文件大小为 0
4. **编码问题** - 特殊的图片编码 PIL 无法识别

### 失败后的行为

1. **首次失败**: 尝试生成缓存 → 失败 → 记录到黑名单 → 返回原图
2. **后续请求**: 检测到在黑名单 → 跳过缓存生成 → 直接返回原图
3. **服务重启**: 自动加载黑名单 → 不会重复尝试失败的图片

### 黑名单管理

```python
from photo_cache_manager import PhotoCacheManager

cache_mgr = PhotoCacheManager()

# 查看失败图片列表
failed_list = cache_mgr.get_failed_images_list()
print(f"失败图片数量: {len(failed_list)}")

# 查看统计信息
stats = cache_mgr.get_cache_stats()
print(f"失败图片: {stats['failed_images_count']}")

# 清空黑名单（允许重试）
cache_mgr.clear_failed_images_list()
```

## 使用方法

### 基础用法

```python
from pathlib import Path
from photo_cache_manager import PhotoCacheManager
from photo_cache_fallback import PhotoCacheFallback

# 初始化
cache_mgr = PhotoCacheManager(
    cache_dir='cache/photos',
    max_cache_size_mb=500
)

# 获取缩略图（带降级）
image_path = Path('<DATA_DIR>/picture/project/product/serial/photo.jpg')
cached_path, is_cached, error = PhotoCacheFallback.get_thumbnail_with_fallback(
    cache_mgr, image_path, size=(300, 300)
)

if cached_path:
    if is_cached:
        print(f"使用缓存: {cached_path}")
    else:
        print(f"使用原图: {cached_path} (原因: {error})")
else:
    print(f"图片不可用: {error}")
```

### Flask API 集成

```python
from flask import send_file
from photo_cache_fallback import PhotoCacheFallback

@app.route('/api/photos/thumbnail/<path:photo_path>')
def get_thumbnail(photo_path):
    image_path = Path(photo_path)
    
    # 获取缩略图（自动降级）
    file_path, is_cached, error = PhotoCacheFallback.get_thumbnail_with_fallback(
        cache_mgr, image_path
    )
    
    if file_path:
        response = send_file(file_path, mimetype='image/jpeg')
        # 添加响应头标识是否使用缓存
        response.headers['X-Cache-Status'] = 'HIT' if is_cached else 'MISS'
        if error:
            response.headers['X-Cache-Error'] = error
        return response
    else:
        return jsonify({'error': error}), 404
```

## 诊断工具

### 1. 扫描损坏图片

```bash
# 在服务器上运行
cd /volume1/mesapp/app_web
python3 diagnose_photos.py <DATA_DIR>/picture

# 查看报告
cat photo_diagnosis_report.txt
```

### 2. 查看缓存统计

```python
stats = cache_mgr.get_cache_stats()
print(f"""
缓存统计:
- 缩略图数量: {stats['thumbnail_count']}
- 压缩图数量: {stats['compressed_count']}
- 总大小: {stats['total_size_mb']:.2f} MB
- 使用率: {stats['usage_percent']:.1f}%
- 失败图片: {stats['failed_images_count']}
""")
```

## 维护操作

### 清理缓存

```python
# 清空所有缓存
cache_mgr.clear_cache()

# 清空失败黑名单（允许重试）
cache_mgr.clear_failed_images_list()
```

### 手动删除缓存

```bash
# 删除所有缓存
rm -rf cache/photos/thumbnails/*
rm -rf cache/photos/compressed/*

# 删除失败黑名单
rm cache/photos/failed_images.txt
```

### 修复损坏图片

1. 运行诊断工具找出损坏文件
2. 删除损坏的图片文件
3. 重新上传正确的图片
4. 清空失败黑名单让系统重试

```bash
# 示例：删除损坏文件
rm "<DATA_DIR>/picture/project/product/serial/broken.jpg"

# 清空黑名单
rm cache/photos/failed_images.txt

# 重启服务
sudo systemctl restart mesapp
```

## 性能优化

### 缓存大小配置

```python
# 默认 500MB
cache_mgr = PhotoCacheManager(max_cache_size_mb=500)

# 大容量服务器可以增加
cache_mgr = PhotoCacheManager(max_cache_size_mb=2000)

# 小容量服务器可以减少
cache_mgr = PhotoCacheManager(max_cache_size_mb=200)
```

### 缓存清理策略

- 自动清理：当缓存超过限制时，删除最久未访问的文件
- 目标大小：清理到最大容量的 80%
- 不影响原图：只删除缓存文件

## 常见问题

### Q: 为什么有些图片每次重启都尝试生成缓存？
A: 旧版本没有黑名单机制。更新后会自动记录失败图片，避免重复尝试。

### Q: 缓存失败会影响用户查看照片吗？
A: 不会。系统会自动降级到原图，用户可以正常查看，只是加载速度可能较慢。

### Q: 如何知道哪些图片使用了原图？
A: 检查响应头 `X-Cache-Status: MISS` 和 `X-Cache-Error`。

### Q: 可以强制重新生成缓存吗？
A: 可以。删除对应的缓存文件和黑名单记录即可。

### Q: 缓存会占用多少空间？
A: 取决于照片数量。一般缩略图约 20-50KB，压缩图约 100-300KB。

## 监控建议

### 日志监控

```bash
# 查看缓存相关日志
tail -f app_web.log | grep photo_cache

# 统计失败次数
grep "生成缩略图失败" app_web.log | wc -l
```

### 定期检查

```bash
# 每周运行一次诊断
0 2 * * 0 cd /volume1/mesapp/app_web && python3 diagnose_photos.py <DATA_DIR>/picture
```

### 告警阈值

- 失败图片数量 > 100：需要检查
- 缓存使用率 > 90%：考虑增加容量
- 缓存命中率 < 50%：检查配置
