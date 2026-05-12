import os
import unittest


ROOT = '/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-feishu-bot'


class DeploymentFilesTests(unittest.TestCase):
    def test_expected_deployment_files_exist(self):
        expected = [
            'scripts/deploy_local.sh',
            'scripts/status_local.sh',
            'scripts/qrmes-feishu-bot.service',
        ]
        for relative in expected:
            self.assertTrue(os.path.exists(os.path.join(ROOT, relative)), relative)


if __name__ == '__main__':
    unittest.main()
