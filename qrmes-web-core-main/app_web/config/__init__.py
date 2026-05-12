"""配置模块

这个包用于组织配置相关的子模块（redis_config, secrets 等）。
主配置对象 config 从父目录的 config.py 导入。
"""

# 解决方案：重命名导入以避免与包名冲突
import sys
import os

# 获取父目录路径并添加到 sys.path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 使用 importlib 动态导入 config.py 模块，避免名称冲突
import importlib.util

config_py_path = os.path.join(parent_dir, 'config.py')

try:
    # 使用 spec 加载 config.py 模块
    spec = importlib.util.spec_from_file_location("config_module", config_py_path)
    if spec and spec.loader:
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)

        # 导出 config 对象
        config = config_module.config
        __all__ = ['config']
    else:
        print(f"[config/__init__.py] 错误: 无法加载 config.py")
        config = None
except Exception as e:
    print(f"[config/__init__.py] 错误: 无法导入 config 对象: {e}")
    print(f"[config/__init__.py] config_py_path: {config_py_path}")
    config = None
