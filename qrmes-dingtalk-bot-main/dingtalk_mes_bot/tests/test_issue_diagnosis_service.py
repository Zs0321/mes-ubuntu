import os
import sqlite3
import tempfile
import unittest

from dingtalk_mes_bot.services.issue_diagnosis_service import IssueDiagnosisService


class FakeProbeService:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def collect(self, targets):
        self.calls.append(tuple(targets))
        return self.payload


class IssueDiagnosisServiceTests(unittest.TestCase):
    def test_can_handle_web_publish(self):
        svc = IssueDiagnosisService(FakeProbeService({}))
        self.assertTrue(svc.can_handle('web发布后打不开'))
        self.assertTrue(svc.can_handle('产线报401怎么查'))
        self.assertFalse(svc.can_handle('今天天气不错'))

    def test_diagnose_h2_serial_with_sqlite_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, 'product_records.db')
            conn = sqlite3.connect(db_path)
            conn.execute('create table product_records(id integer primary key, product_serial text, project_name text, product_type text)')
            conn.execute("insert into product_records(product_serial, project_name, product_type) values ('SN123456', '项目A', '电机')")
            conn.commit()
            conn.close()
            probe = FakeProbeService({'qrmes-web-core': {'health': [], 'files': [], 'scripts': []}})
            svc = IssueDiagnosisService(probe, h2_db_path=db_path)
            reply = svc.diagnose('SN123456 产品记录库查不到')
            self.assertIn('SQLite定点诊断', reply)
            self.assertIn('项目A', reply)
            self.assertEqual([('qrmes-web-core',)], probe.calls)

    def test_diagnose_401_returns_login_specific_guidance(self):
        probe = FakeProbeService({'qrmes-web-core': {'health': [], 'files': [], 'scripts': []}})
        svc = IssueDiagnosisService(probe)
        reply = svc.diagnose('产线报401怎么查')
        self.assertIn('登录/权限', reply)
        self.assertIn('Authorization', reply)
        self.assertIn('账号权限不足', reply)


if __name__ == '__main__':
    unittest.main()
