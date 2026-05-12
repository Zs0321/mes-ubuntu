# tests/e2e/config.py
TEST_CONFIG = {
    'base_url': 'http://172.16.30.2:8891',
    'test_user': {
        'username': 'zhiqiang.zhu',
        'password': 'Clt@123456'
    },
    'ssh': {
        'host': '172.16.30.2',
        'port': 30001,
        'user': 'panovation',
        'password': 'Clt2020clt',
        'test_path': '/volume2/MES/test'
    },
    'timeouts': {
        'default': 30000,
        'navigation': 60000
    },
    'screenshots_dir': 'test_results/screenshots',
    'reports_dir': 'test_results/reports'
}
