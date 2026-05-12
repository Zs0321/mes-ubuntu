# tests/e2e/utils/health_checker.py
import subprocess
import requests
import time

class HealthChecker:
    def __init__(self, ssh_config):
        self.ssh_config = ssh_config

    def check_process(self):
        """检查进程是否运行"""
        cmd = f"sshpass -p {self.ssh_config['password']} ssh -o StrictHostKeyChecking=no -p {self.ssh_config['port']} {self.ssh_config['user']}@{self.ssh_config['host']} \"ps aux | grep 'python.*mesapp.py' | grep -v grep\""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0

    def check_logs(self):
        """检查日志是否健康"""
        cmd = f"sshpass -p {self.ssh_config['password']} ssh -o StrictHostKeyChecking=no -p {self.ssh_config['port']} {self.ssh_config['user']}@{self.ssh_config['host']} \"tail -50 {self.ssh_config['test_path']}/logs/app.log\""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        logs = result.stdout

        # 检查错误标志
        error_keywords = ['ERROR', 'Exception', 'Traceback', 'CRITICAL']
        for keyword in error_keywords:
            if keyword in logs:
                return False, f"发现错误关键字: {keyword}"

        # 检查启动成功标志
        if 'Running on http://172.16.30.2:8891' in logs:
            return True, "服务启动成功"

        return False, "未找到启动成功标志"

    def check_http(self, base_url):
        """HTTP 健康检查"""
        try:
            response = requests.get(f"{base_url}/api/h2/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return True, "HTTP 健康检查通过"
            return False, f"HTTP 返回异常: {response.status_code}"
        except Exception as e:
            return False, f"HTTP 请求失败: {str(e)}"

    def check_all(self, base_url):
        """执行所有健康检查"""
        results = {
            'process': self.check_process(),
            'logs': self.check_logs(),
            'http': self.check_http(base_url)
        }

        all_healthy = all([
            results['process'],
            results['logs'][0],
            results['http'][0]
        ])

        return all_healthy, results
