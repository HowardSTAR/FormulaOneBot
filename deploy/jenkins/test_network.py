"""Check CI DNS override wiring with a fake Docker CLI; never send messages."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from cli_fixtures import shell_path, cli_environment, write_fake_cli


class NetworkOverridesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = shell_path()

    def scenario(self, config):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'network.env').write_text(config, encoding='utf-8', newline='\n')
            write_fake_cli(root / 'docker', '#!/usr/bin/python3\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ["CALLS"]).write_text(json.dumps(sys.argv[1:]))\n')
            env = cli_environment(root, WORKSPACE=str(root), CI_SCRIPTS=str(root), CALLS=str(root / 'calls.json'))
            result = subprocess.run([self.shell, str(Path(__file__).with_name('run-ci.sh').resolve()), 'notify'],
                                    env=env, capture_output=True, text=True, timeout=10)
            calls = json.loads((root / 'calls.json').read_text()) if (root / 'calls.json').exists() else []
            return result, calls

    def test_allowlisted_hosts_are_passed_to_container(self):
        result, calls = self.scenario('deb.debian.org=199.232.42.132\napi.telegram.org=149.154.167.220\nother.example=1.1.1.1\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('deb.debian.org=199.232.42.132', calls)
        self.assertIn('api.telegram.org=149.154.167.220', calls)
        self.assertNotIn('other.example=1.1.1.1', calls)

    def test_invalid_override_stops_before_starting_container(self):
        result, calls = self.scenario('api.telegram.org=bad-address\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_empty_override_preserves_normal_dns(self):
        result, calls = self.scenario('')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('--add-host', calls)


if __name__ == '__main__':
    unittest.main(verbosity=2)
