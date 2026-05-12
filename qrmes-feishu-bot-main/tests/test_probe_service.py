import os
import sqlite3
import tempfile
import unittest

from feishu_mes_bot.services.probe_service import ProbeService
from feishu_mes_bot.services.repository_catalog import RepositoryCatalog


class ProbeServiceTests(unittest.TestCase):
    def test_collect_includes_log_tail_and_sqlite_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = os.path.join(tmp, 'qrmes-web-core')
            os.makedirs(repo_root)
            log_path = os.path.join(repo_root, 'runtime.log')
            with open(log_path, 'w', encoding='utf-8') as fh:
                fh.write('line1\nline2\nTraceback sample\n')
            db_path = os.path.join(repo_root, 'unified.db')
            conn = sqlite3.connect(db_path)
            conn.execute('create table process_photos(id integer primary key, product_serial text)')
            conn.execute("insert into process_photos(product_serial) values ('SN001')")
            conn.commit()
            conn.close()

            catalog = RepositoryCatalog()
            catalog.targets['qrmes-web-core'].file_paths = ('runtime.log', 'unified.db')
            probe = ProbeService(tmp, catalog)

            report = probe.collect(['qrmes-web-core'])
            files = report['qrmes-web-core']['files']
            log_entry = next(item for item in files if item['path'] == 'runtime.log')
            db_entry = next(item for item in files if item['path'] == 'unified.db')
            self.assertIn('Traceback sample', log_entry['tail'])
            self.assertEqual('sqlite', db_entry['kind'])
            self.assertEqual(1, db_entry['tables']['process_photos'])


if __name__ == '__main__':
    unittest.main()
