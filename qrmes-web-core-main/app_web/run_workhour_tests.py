#!/usr/bin/env python3
"""运行工时计算模块测试"""
import sys
import os
import traceback

# 确保 app_web 在 path 中
app_web = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_web)

# 先手动 import 测试模块，看看有没有报错
try:
    from tests import test_mes_readonly_work_hours
    print(f"OK: loaded local MES work-hour tests ({len(dir(test_mes_readonly_work_hours))} names)")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

import unittest
loader = unittest.TestLoader()
suite = unittest.TestSuite(
    [
        loader.loadTestsFromModule(test_mes_readonly_work_hours),
    ]
)
print(f"Tests found: {suite.countTestCases()}")

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
