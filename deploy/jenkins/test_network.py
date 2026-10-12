"""Check CI DNS override wiring with a fake Docker CLI; never send messages."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class NetworkOverridesTests(unittest.TestCase):
    def scenario(self, config):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'network.env').write_text(config)
            cli = root / 'docker'
            cli.write_text('#!/usr/bin/python3\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ["CALLS"]).write_text(json.dumps(sys.argv[1:]))\n')
            cli.chmod(0o700)
            env = dict(os.environ, WORKSPACE=str(root), CI_SCRIPTS=str(root),
                       PATH=str(root)+os.pathsep+os.environ['PATH'], CALLS=str(root / 'calls.json'))
            result = subprocess.run(['bash', str(Path(__file__).with_name('run-ci.sh').resolve()), 'notify'],
                                    env=env, capture_output=True, text=True, timeout=10)
            calls = json.loads((root / 'calls.json').read_text()) if (root / 'calls.json').exists() else []
            return result.returncode, calls

    def test_allowlisted_hosts_are_passed_to_container(self):
        code, calls = self.scenario('deb.debian.org=199.232.42.132\napi.telegram.org=149.154.167.220\nother.example=1.1.1.1\n')
        self.assertEqual(code, 0)
        self.assertIn('deb.debian.org=199.232.42.132', calls)
        self.assertIn('api.telegram.org=149.154.167.220', calls)
        self.assertNotIn('other.example=1.1.1.1', calls)

    def test_invalid_override_stops_before_starting_container(self):
        code, calls = self.scenario('api.telegram.org=bad-address\n')
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, [])

    def test_empty_override_preserves_normal_dns(self):
        code, calls = self.scenario('')
        self.assertEqual(code, 0)
        self.assertNotIn('--add-host', calls)


if __name__ == '__main__':
    unittest.main(verbosity=2)
