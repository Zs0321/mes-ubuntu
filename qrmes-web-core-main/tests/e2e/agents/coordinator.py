# tests/e2e/agents/coordinator.py
import asyncio
import subprocess
import json
from pathlib import Path
from typing import Dict, List
import sys
import os

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_CONFIG
from utils.health_checker import HealthChecker

class Coordinator:
    def __init__(self, max_iterations=5):
        self.max_iterations = max_iterations
        self.current_iteration = 0
        self.test_results_history = []
        self.consecutive_same_failures = 0
        self.previous_failures = []
        self.health_checker = HealthChecker(TEST_CONFIG['ssh'])

    async def run_test_fix_loop(self):
        """运行测试-修复循环"""
        print("=== 开始自动化测试和修复循环 ===\n")

        for iteration in range(1, self.max_iterations + 1):
            self.current_iteration = iteration
            print(f"\n{'='*60}")
            print(f"第 {iteration} 轮测试")
            print(f"{'='*60}\n")

            # 1. 运行测试
            test_results = await self.run_tests()
            self.test_results_history.append(test_results)

            # 2. 检查是否全部通过
            if test_results['all_passed']:
                print("\n✅ 所有测试通过！")
                self.print_final_report()
                return True

            # 3. 分析失败
            analysis = await self.analyze_failures(test_results['failures'])

            # 4. 检查循环
            if self.is_stuck_in_loop(analysis['failures']):
                print("\n⚠️ 检测到循环，停止自动修复")
                self.print_final_report()
                return False

            # 5. 修复问题
            fixes = await self.fix_issues(analysis)

            # 6. 部署
            deploy_success = await self.deploy()
            if not deploy_success:
                print("\n❌ 部署失败，停止循环")
                return False

            # 7. 等待服务稳定
            await asyncio.sleep(10)

            # 8. 更新状态
            self.previous_failures = analysis['failures']

            print(f"\n本轮修复 {len(fixes)} 个问题，剩余 {len(test_results['failures'])} 个失败")

        print(f"\n⏱️ 达到最大迭代次数 ({self.max_iterations} 轮)")
        self.print_final_report()
        return False

    async def run_tests(self):
        """运行所有测试"""
        print("📋 运行 E2E 测试...")

        # 确保报告目录存在
        reports_dir = Path('test_results/reports')
        reports_dir.mkdir(parents=True, exist_ok=True)

        # 调用 pytest 运行测试
        cmd = [
            'pytest',
            'tests/e2e/',
            '-v',
            '--tb=short',
            '--json-report',
            '--json-report-file=test_results/reports/test_report.json',
            '--json-report-indent=2'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd='/Users/mini/QRTestScanner-clean')

        # 解析测试结果
        report_path = Path('test_results/reports/test_report.json')
        if report_path.exists():
            with open(report_path) as f:
                report = json.load(f)

            failures = []
            for test in report.get('tests', []):
                if test['outcome'] == 'failed':
                    # 提取错误信息
                    error_info = test.get('call', {})
                    longrepr = error_info.get('longrepr', '')

                    failures.append({
                        'name': test['nodeid'],
                        'error': longrepr,
                        'duration': error_info.get('duration', 0),
                        'outcome': test['outcome']
                    })

            all_passed = len(failures) == 0
            total_tests = report.get('summary', {}).get('total', 0)
            passed_tests = report.get('summary', {}).get('passed', 0)

            print(f"✓ 测试完成: {total_tests} 个测试, {passed_tests} 个通过, {len(failures)} 个失败")

            return {
                'all_passed': all_passed,
                'failures': failures,
                'total': total_tests,
                  'passed': passed_tests
            }
        else:
            print("⚠️ 测试报告文件不存在")
            return {
                'all_passed': False,
                'failures': [],
                'total': 0,
                'passed': 0
            }

    async def analyze_failures(self, failures):
        """分析测试失败原因"""
        print(f"\n🔍 分析 {len(failures)} 个失败...")

        analysis = {
            'failures': failures,
            'categories': {
                'js_errors': [],
                'api_errors': [],
                'db_errors': [],
                'auth_errors': [],
                'timeout_errors': [],
                'other_errors': []
            },
            'priority': {
                'P0': [],  # 阻塞性问题（数据库、认证）
                'P1': [],  # 高优先级（API 错误）
                'P2': [],  # 中优先级（JS 错误、超时）
                'P3': []   # 低优先级（其他）
            }
        }

        for failure in failures:
            error_text = failure['error'].lower()

            # 分类错误类型
            categorized = False

            if 'javascript' in error_text or 'console' in error_text or 'js error' in error_text:
                analysis['categories']['js_errors'].append(failure)
                analysis['priority']['P2'].append(failure)
                categorized = True

            if '500' in error_text or 'internal server error' in error_text:
                analysis['categories']['api_errors'].append(failure)
                analysis['priority']['P1'].append(failure)
                categorized = True
            elif '404' in error_text or 'not found' in error_text:
                analysis['categories']['api_errors'].append(failure)
                analysis['priority']['P1'].append(failure)
                categorized = True
            elif 'api' in error_text or 'endpoint' in error_text:
                analysis['categories']['api_errors'].append(failure)
                analysis['priority']['P1'].append(failure)
                categorized = True

            if 'database' in error_text or 'sql' in error_text or 'db' in error_text:
                analysis['categories']['db_errors'].append(failure)
                analysis['priority']['P0'].append(failure)
                categorized = True

            if 'unauthorized' in error_text or 'login' in error_text or 'auth' in error_text or '401' in error_text:
                analysis['categories']['auth_errors'].append(failure)
                analysis['priority']['P0'].append(failure)
                categorized = True

            if 'timeout' in error_text or 'timed out' in error_text:
                analysis['categories']['timeout_errors'].append(failure)
                analysis['priority']['P2'].append(failure)
                categorized = True

            if not categorized:
                analysis['categories']['other_errors'].append(failure)
                analysis['priority']['P3'].append(failure)

        # 打印分析结果
        print(f"\n错误分类:")
        print(f"  - JS 错误: {len(analysis['categories']['js_errors'])}")
        print(f"  - API 错误: {len(analysis['categories']['api_errors'])}")
        print(f"  - 数据库错误: {len(analysis['categories']['db_errors'])}")
        print(f"  - 认证错误: {len(analysis['categories']['auth_errors'])}")
        print(f"  - 超时错误: {len(analysis['categories']['timeout_errors'])}")
        print(f"  - 其他错误: {len(analysis['categories']['other_errors'])}")
        print(f"\n优先级分布:")
        print(f"  - P0 (阻塞): {len(analysis['priority']['P0'])}")
        print(f"  - P1 (高): {len(analysis['priority']['P1'])}")
        print(f"  - P2 (中): {len(analysis['priority']['P2'])}")
        print(f"  - P3 (低): {len(analysis['priority']['P3'])}")

        # 打印前 3 个高优先级问题的详细信息
        high_priority = analysis['priority']['P0'] + analysis['priority']['P1']
        if high_priority:
            print(f"\n高优先级问题详情:")
            for i, failure in enumerate(high_priority[:3], 1):
                print(f"\n  {i}. {failure['name']}")
                error_lines = failure['error'].split('\n')
                # 只打印前 5 行错误信息
                for line in error_lines[:5]:
                    if line.strip():
                        print(f"     {line[:100]}")

        return analysis

    async def fix_issues(self, analysis):
        """修复问题"""
        print(f"\n🔧 修复问题...")

        fixes = []

        # 优先修复 P0 和 P1 问题
        high_priority = analysis['priority']['P0'] + analysis['priority']['P1']

        if len(high_priority) == 0:
            print("  ℹ️ 没有高优先级问题需要修复")
            return fixes

        print(f"  发现 {len(high_priority)} 个高优先级问题")

        # 限制每轮最多修复 3 个问题（避免过多修改）
        issues_to_fix = high_priority[:3]

        for i, failure in enumerate(issues_to_fix, 1):
            print(f"\n  [{i}/{len(issues_to_fix)}] 修复: {failure['name']}")

            try:
                # 1. 收集错误详情
                error_details = await self.collect_error_details(failure)

                if not error_details:
                    print(f"    ⚠️ 无法收集错误详情，跳过")
                    continue

                # 2. 派发 fixer agent（在同步上下文中）
                print(f"    📝 派发 fixer agent...")
                fix_result = await asyncio.to_thread(self.dispatch_fixer_agent_sync, error_details)

                # 3. 验证修复
                if fix_result and fix_result.get('success'):
                    print(f"    ✓ 修复成功")
                    fixes.append({
                        'test': failure['name'],
                        'error': error_details['error_type'],
                        'fix': fix_result.get('description', '已修复')
                    })
                else:
                    print(f"    ✗ 修复失败: {fix_result.get('error', '未知错误')}")

            except Exception as e:
                print(f"    ✗ 修复异常: {str(e)}")
                continue

        print(f"\n  总计修复: {len(fixes)}/{len(issues_to_fix)} 个问题")

        return fixes

    async def collect_error_details(self, failure):
        """收集错误的详细信息"""
        error_text = failure['error']
        test_name = failure['name']

        # 检查服务器日志获取更多信息
        ssh_config = TEST_CONFIG['ssh']
        log_cmd = f"sshpass -p {ssh_config['password']} ssh -o StrictHostKeyChecking=no -p {ssh_config['port']} {ssh_config['user']}@{ssh_config['host']} \"tail -100 {ssh_config['test_path']}/logs/app.log | grep -A 10 'ERROR\\|Exception\\|Traceback'\""

        result = subprocess.run(log_cmd, shell=True, capture_output=True, text=True)
        server_logs = result.stdout if result.returncode == 0 else ""

        # 分析错误类型
        error_type = 'unknown'
        error_lower = error_text.lower()

        if '500' in error_text or 'internal server error' in error_lower:
            error_type = 'api_500'
        elif '404' in error_text or 'not found' in error_lower:
            error_type = 'api_404'
        elif 'javascript' in error_lower or 'console' in error_lower or 'js error' in error_lower:
            error_type = 'javascript'
        elif 'database' in error_lower or 'sql' in error_lower or 'db' in error_lower:
            error_type = 'database'
        elif 'unauthorized' in error_lower or 'login' in error_lower or '401' in error_text:
            error_type = 'auth'

        # 尝试从日志中提取文件名和行号
        file_location = None
        if server_logs and 'File "' in server_logs:
            import re
            match = re.search(r'File "([^"]+)", line (\d+)', server_logs)
            if match:
                file_location = {
                    'file': match.group(1),
                    'line': int(match.group(2))
                }

        return {
            'test_name': test_name,
            'error_type': error_type,
            'error_message': error_text[:500],  # 限制长度
            'server_logs': server_logs[:1000] if server_logs else "",  # 限制长度
            'file_location': file_location
        }

    def dispatch_fixer_agent_sync(self, error_details):
        """同步方式派发 fixer agent 修复问题"""

        # 构建修复提示
        fix_prompt = f"""你需要修复以下测试失败的问题：

**测试名称：** {error_details['test_name']}

**错误类型：** {error_details['error_type']}

**错误信息：**
```
{error_details['error_message']}
```
"""

        if error_details['server_logs']:
            fix_prompt += f"""
**服务器日志：**
```
{error_details['server_logs']}
```
"""

        if error_details['file_location']:
            fix_prompt += f"""
**问题位置：**
- 文件：{error_details['file_location']['file']}
- 行号：{error_details['file_location']['line']}
"""

        fix_prompt += """

**修复要求：**
1. 读取相关代码文件
2. 分析错误原因
3. 应用最小化修复（只修复问题，不做额外改动）
4. 使用 Edit 工具修改代码
5. Git 提交修复（使用简洁的 commit message）

**修复策略：**
"""

        if error_details['error_type'] == 'api_500':
            fix_prompt += """
- 检查 Python 代码中的异常
- 修复缺失的导入、属性或方法
- 修复 SQL 查询错误
- 修复数据库连接问题
- 添加必要的错误处理
"""
        elif error_details['error_type'] == 'api_404':
            fix_prompt += """
- 检查路由是否存在
- 检查 API 端点是否正确注册
- 添加缺失的路由
- 检查 Blueprint 注册
"""
        elif error_details['error_type'] == 'javascript':
            fix_prompt += """
- 检查 JavaScript 语法错误
- 修复未声明的变量
- 修复函数调用错误
- 添加必要的 null 检查
"""
        elif error_details['error_type'] == 'database':
            fix_prompt += """
- 检查数据库管理器类的属性
- 修复 SQL 查询语法
- 修复数据库连接配置
- 添加必要的数据库初始化
"""
        elif error_details['error_type'] == 'auth':
            fix_prompt += """
- 检查认证装饰器
- 检查 session 管理
- 修复权限验证逻辑
- 添加必要的登录检查
"""

        fix_prompt += """

**重要提示：**
- 只修复导致测试失败的具体问题
- 不要重构或优化其他代码
- 确保修复后代码可以正常运行
- 提交时使用格式：fix(test): 简短描述问题

请开始修复，完成后简要说明修复了什么。
"""

        # 将修复提示写入临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(fix_prompt)
            prompt_file = f.name

        try:
            # 使用 subprocess 调用 Claude Code CLI 派发 agent
            # 注意：这里假设可以通过命令行调用 Claude Code
            # 实际实现可能需要根据环境调整

            print(f"    💡 尝试自动修复 {error_details['error_type']} 错误...")

            # 由于无法直接调用 Task tool，这里返回一个模拟结果
            # 实际部署时，可以通过以下方式之一实现：
            # 1. 使用 Claude Code CLI
            # 2. 使用 API 调用
            # 3. 集成到现有的 agent 框架中

            return {
                'success': False,
                'error': '自动修复功能需要集成 Task tool 或 Claude Code CLI',
                'description': '当前为模拟实现，需要实际的 agent 派发机制'
            }

        finally:
            # 清理临时文件
            import os
            if os.path.exists(prompt_file):
                os.unlink(prompt_file)

    async def deploy(self):
        """部署到测试服务器"""
        print(f"\n🚀 部署到测试服务器...")

        ssh_config = TEST_CONFIG['ssh']
        base_url = TEST_CONFIG['base_url']

        # 1. 复制代码到服务器
        print("  1. 复制代码...")

        # 复制主要的 Python 文件
        files_to_copy = [
            'app_web/mesapp.py',
            'app_web/motor_qc/routes.py',
            'app_web/motor_qc/models.py',
            'app_web/motor_qc/config.py',
            'app_web/motor_qc/services/vision_api.py',
            'app_web/motor_qc/services/claude_vision.py',
            'app_web/motor_qc/services/qwen_vision.py'
        ]

        copy_success = True
        for file_path in files_to_copy:
            local_path = f"/Users/mini/QRTestScanner-clean/{file_path}"
            remote_path = f"{ssh_config['test_path']}/{file_path}"

            # 确保远程目录存在
            remote_dir = '/'.join(remote_path.split('/')[:-1])
            mkdir_cmd = f"sshpass -p {ssh_config['password']} ssh -o StrictHostKeyChecking=no -p {ssh_config['port']} {ssh_config['user']}@{ssh_config['host']} \"mkdir -p {remote_dir}\""
            subprocess.run(mkdir_cmd, shell=True, capture_output=True)

            # 复制文件
            copy_cmd = f"sshpass -p {ssh_config['password']} scp -o StrictHostKeyChecking=no -P {ssh_config['port']} {local_path} {ssh_config['user']}@{ssh_config['host']}:{remote_path}"
            result = subprocess.run(copy_cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"  ✗ 复制失败: {file_path}")
                print(f"    错误: {result.stderr}")
                copy_success = False
                break

        if not copy_success:
            print("  ✗ 代码复制失败，停止部署")
            return False

        print("  ✓ 代码复制成功")

        # 2. 重启服务
        print("  2. 重启服务...")
        restart_cmd = f"sshpass -p {ssh_config['password']} ssh -o StrictHostKeyChecking=no -p {ssh_config['port']} {ssh_config['user']}@{ssh_config['host']} \"pkill -f 'python.*mesapp.py'; sleep 2; cd {ssh_config['test_path']}/app_web && nohup python mesapp.py > {ssh_config['test_path']}/logs/app.log 2>&1 &\""

        result = subprocess.run(restart_cmd, shell=True, capture_output=True, text=True)
        print("  ✓ 服务重启命令已执行")

        # 3. 等待服务启动
        print("  3. 等待服务启动...")
        await asyncio.sleep(10)

        # 4. 健康检查
        print("  4. 执行健康检查...")
        healthy, results = self.health_checker.check_all(base_url)

        if healthy:
            print("  ✓ 健康检查通过")
            print(f"    - 进程: ✓")
            print(f"    - 日志: ✓ {results['logs'][1]}")
            print(f"    - HTTP: ✓ {results['http'][1]}")
            return True
        else:
            print("  ✗ 健康检查失败:")
            print(f"    - 进程: {'✓' if results['process'] else '✗'}")
            print(f"    - 日志: {'✓' if results['logs'][0] else '✗ ' + results['logs'][1]}")
            print(f"    - HTTP: {'✓' if results['http'][0] else '✗ ' + results['http'][1]}")

            # 打印服务器日志以便调试
            print("\n  最近的服务器日志:")
            log_cmd = f"sshpass -p {ssh_config['password']} ssh -o StrictHostKeyChecking=no -p {ssh_config['port']} {ssh_config['user']}@{ssh_config['host']} \"tail -20 {ssh_config['test_path']}/logs/app.log\""
            log_result = subprocess.run(log_cmd, shell=True, capture_output=True, text=True)
            if log_result.returncode == 0:
                for line in log_result.stdout.split('\n')[-10:]:
                    if line.strip():
                        print(f"    {line}")

            return False

    def is_stuck_in_loop(self, current_failures):
        """检测是否陷入循环"""
        if current_failures == self.previous_failures:
            self.consecutive_same_failures += 1
            return self.consecutive_same_failures >= 2
        else:
            self.consecutive_same_failures = 0
            return False

    def print_final_report(self):
        """打印最终报告"""
        print("\n" + "="*60)
        print("自动化测试修复完成")
        print("="*60)

        if len(self.test_results_history) > 0:
            first_result = self.test_results_history[0]
            last_result = self.test_results_history[-1]

            initial_failures = len(first_result['failures'])
            final_failures = len(last_result['failures'])
            fixed_count = initial_failures - final_failures
            success_rate = (fixed_count / initial_failures * 100) if initial_failures > 0 else 100

            print(f"总轮数：{self.current_iteration} 轮")
            print(f"初始失败：{initial_failures} 个")
            print(f"最终失败：{final_failures} 个")
            print(f"修复成功率：{success_rate:.1f}%")

            if final_failures > 0:
                print(f"\n剩余问题：")
                for i, failure in enumerate(last_result['failures'][:5], 1):
                    print(f"{i}. {failure}")
