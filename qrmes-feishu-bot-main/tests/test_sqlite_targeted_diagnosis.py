import os
import sqlite3
import tempfile
import unittest

from feishu_mes_bot.services.issue_diagnosis_service import IssueDiagnosisService
from feishu_mes_bot.services.repository_catalog import RepositoryCatalog


class FakeProbeService:
    def __init__(self, reply):
        self.reply = reply

    def collect(self, targets):
        return self.reply


class SqliteTargetedDiagnosisTests(unittest.TestCase):
    def test_diagnose_h2_serial_uses_real_sqlite_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, 'product_records.db')
            conn = sqlite3.connect(db_path)
            conn.execute('create table product_records(id integer primary key, product_serial text, project_name text, product_type text)')
            conn.execute("insert into product_records(product_serial, project_name, product_type) values ('SN123456', '项目A', '电机')")
            conn.commit()
            conn.close()

            catalog = RepositoryCatalog()
            catalog.targets['qrmes-web-core'].file_paths = ('runtime.log',)
            catalog.sqlite_diagnostics = {
                'h2_database': [
                    {
                        'path': db_path,
                        'table': 'product_records',
                        'lookup_column': 'product_serial',
                        'extract_pattern': 'SN\d{6}',
                        'select_columns': ['product_serial', 'project_name', 'product_type'],
                        'label': 'product_records',
                    }
                ]
            }
            service = IssueDiagnosisService(catalog, FakeProbeService({'qrmes-web-core': {'health': [], 'scripts': [], 'files': []}}))
            reply = service.diagnose('SN123456 产品记录库查不到')
            self.assertIn('SQLite定点诊断', reply)
            self.assertIn('项目A', reply)
            self.assertIn('电机', reply)


if __name__ == '__main__':
    unittest.main()
