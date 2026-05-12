import os
import sqlite3
import tempfile
import unittest

from dingtalk_mes_bot.services.project_prefix_service import ProjectPrefixService


class ProjectPrefixServiceTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('create table projects (id integer primary key, project_name text)')
        cur.execute('create table product_types (id integer primary key, project_id integer, type_name text)')
        cur.execute('create table serial_rules (id integer primary key, product_type_id integer, rule_prefix text, normalized_prefix text)')
        cur.execute("insert into projects(id, project_name) values(1, '??3.5T?15??(??????)')")
        cur.execute("insert into product_types(id, project_id, type_name) values(1, 1, '?????')")
        cur.execute("insert into serial_rules(product_type_id, rule_prefix, normalized_prefix) values(1, 'GenesisLiGFLF10C', 'genesisligflf10c')")
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_resolve_for_query_corrects_single_missing_prefix_character(self):
        service = ProjectPrefixService(self.db_path)

        corrected_serial, matches = service.resolve_for_query('Genesis-LiGFL10C2026041000461')

        self.assertEqual('GenesisLiGFLF10C2026041000461', corrected_serial)
        self.assertEqual(1, len(matches))
        self.assertEqual('?????', matches[0].product_type)

    def test_resolve_for_query_rejects_unmatched_work_order_value(self):
        service = ProjectPrefixService(self.db_path)

        corrected_serial, matches = service.resolve_for_query('MO001104')

        self.assertEqual('MO001104', corrected_serial)
        self.assertEqual((), matches)


if __name__ == '__main__':
    unittest.main()
