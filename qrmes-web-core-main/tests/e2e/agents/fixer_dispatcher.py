# tests/e2e/agents/fixer_dispatcher.py
"""
Fixer Agent Dispatcher - 负责派发修复 agent
由于 Task tool 需要在同步上下文中调用，这个模块提供了独立的派发接口
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))


def dispatch_fixer_agent(error_details):
    """
    派发 fixer agent 来修复代码问题

    这个函数在同步上下文中运行，可以直接调用 Task tool

    Args:
        error_details: 包含错误详情的字典
            - test_name: 测试名称
            - error_type: 错误类型
            - error_message: 错误信息
            - server_logs: 服务器日志
            - file_location: 文件位置（可选）

    Returns:
        dict: 修复结果
            - success: 是否成功
            - description: 修复描述
            - error: 错误信息（如果失败）
    """

    # 构建修复提示
    fix_prompt = f"""你需要修复以下测试失败的问题：

**工作目录：** /Users/mini/QRTestScanner-clean

**测试名称：** {error_details['test_name']}

**错误类型：** {error_details['error_type']}

**错误信息：**
```
{error_details['error_message']}
```
"""

    if error_details.get('server_logs'):
        fix_prompt += f"""
**服务器日志：**
```
{error_details['server_logs']}
```
"""

    if error_details.get('file_location'):
        fix_prompt += f"""
**问题位置：**
- 文件：{error_details['file_location']['file']}
- 行号：{error_details['file_location']['line']}
"""

    fix_prompt += """

**修复要求：**
1. 读取相关代码文件（使用 Read 工具）
2. 分析错误原因
3. 应用最小化修复（只修复问题，不做额外改动）
4. 使用 Edit 工具修改代码
5. Git 提交修复（使用简洁的 commit message）

**修复策略：**
"""

    if error_details['error_type'] == 'api_500':
        fix_prompt += """
- 检查 Python 代码中的异常和 traceback
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

    try:
        # 这里需要导入 Task tool
        # 注意：这个导入只在实际的 Claude Code 环境中有效
        # 在测试环境中可能需要 mock

        # 尝试导入 Task 功能
        try:
            # 在 Claude Code 环境中，可以通过特殊方式调用 Task
            # 这里使用一个简化的实现

            # 方案：使用 subprocess 调用 Python 脚本来派发 Task
            import subprocess
            import json
            import tempfile

            # 创建临时文件保存提示
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(fix_prompt)
                prompt_file = f.name

            # 创建一个 Python 脚本来调用 Task tool
            task_script = f"""
import sys
sys.path.insert(0, '/Users/mini/QRTestScanner-clean')

# 读取提示
with open('{prompt_file}', 'r') as f:
    prompt = f.read()

# 这里应该调用 Task tool
# 由于环境限制，返回模拟结果
result = {{
    'success': False,
    'error': 'Task tool 需要在 Claude Code 主进程中调用',
    'description': '当前环境无法直接派发 agent'
}}

import json
print(json.dumps(result))
"""

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(task_script)
                script_file = f.name

            # 执行脚本
            result = subprocess.run(
                ['python', script_file],
                capture_output=True,
                text=True,
                timeout=300  # 5 分钟超时
            )

            # 清理临时文件
            os.unlink(prompt_file)
            os.unlink(script_file)

            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            else:
                return {
                    'success': False,
                    'error': f'脚本执行失败: {result.stderr}',
                    'description': '无法派发 fixer agent'
                }

        except ImportError:
            # Task tool 不可用，返回说明
            return {
                'success': False,
                'error': 'Task tool 不可用',
                'description': '需要在 Claude Code 环境中运行'
            }

    except Exception as e:
        return {
            'success': False,
            'error': f'派发 agent 时发生异常: {str(e)}',
            'description': '修复失败'
        }


# 用于测试的主函数
if __name__ == '__main__':
    # 测试用例
    test_error = {
        'test_name': 'tests/e2e/auth/test_authentication.py::test_login',
        'error_type': 'api_500',
        'error_message': 'Internal Server Error',
        'server_logs': 'ERROR: AttributeError: object has no attribute "db_path"',
        'file_location': {
            'file': 'app_web/mesapp.py',
            'line': 2983
        }
    }

    result = dispatch_fixer_agent(test_error)
    print(f"修复结果: {result}")
