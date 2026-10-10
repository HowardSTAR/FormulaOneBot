"""Run image cleanup against a fake Docker daemon; no real images are removed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


FAKE_DOCKER = r"""#!/usr/bin/python3
import json, os, pathlib, sys
sys.stdout.reconfigure(newline='\n')
p = pathlib.Path(os.environ['VALIDATION_DIR'])
args = sys.argv[1:]
with (p / 'calls.jsonl').open('a') as f:
    f.write(json.dumps(args) + '\n')
mode = os.environ['VALIDATION_MODE']
if args[:2] == ['image', 'ls']:
    if '--quiet' in args:
        print('sha256:current' if args[-1] == 'formulaonebot-app:latest' else 'sha256:rollback')
    elif '--filter' in args:
        print('sha256:dangling')
    else:
        print('''sha256:current formulaonebot-app:latest
sha256:current formulaonebot-ci:100
sha256:rollback formulaonebot-rollback:previous
sha256:stopped formulaonebot-ci:99
sha256:old formulaonebot-ci:98
sha256:legacy formulaonebot-web:old
sha256:oldtag formulaonebot-app:old
sha256:dangling <none>:<none>
sha256:unknown <none>:<none>
sha256:other redis:old''')
elif args[:2] == ['image', 'inspect']:
    if mode == 'tag_inspect_failure': sys.exit(1)
    print('sha256:current' if args[2] == 'formulaonebot-app:latest' else 'sha256:rollback')
elif args[:2] == ['ps', '-aq']:
    print('stopped-container')
elif args[0] == 'inspect':
    if mode == 'container_inspect_failure': sys.exit(1)
    print('sha256:stopped')
elif args[:2] == ['image', 'rm']:
    if mode == 'remove_failure': sys.exit(1)
else:
    sys.exit('Unexpected Docker command: ' + repr(args))
"""


class ImageCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = shutil.which('bash')
        if os.name == 'nt':
            candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe'
            if candidate.is_file():
                cls.shell = str(candidate)
        if cls.shell is None:
            raise unittest.SkipTest('Image cleanup tests require Bash')

    def scenario(self, mode='success'):
        with tempfile.TemporaryDirectory(prefix='f1hub-cleanup-') as tmp:
            root = Path(tmp)
            interpreter = '/usr/bin/env python' if os.name == 'nt' else sys.executable
            cli = root / 'docker'
            cli.write_text(FAKE_DOCKER.replace('/usr/bin/python3', interpreter), encoding='utf-8')
            cli.chmod(0o700)
            env = dict(os.environ,
                       PATH=os.pathsep.join((str(root), str(Path(sys.executable).parent), os.environ['PATH'])),
                       VALIDATION_DIR=str(root), VALIDATION_MODE=mode)
            script = Path(__file__).with_name('cleanup-images.sh').read_text()
            process = subprocess.run([self.shell], input=script, text=True,
                                     capture_output=True, env=env, timeout=30)
            calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
            return process.returncode, [call for call in calls if call[:2] == ['image', 'rm']]

    def test_cleanup_preserves_current_rollback_containers_and_unrelated_images(self):
        code, removed = self.scenario()
        self.assertEqual(code, 0)
        self.assertEqual(removed, [
            ['image', 'rm', 'formulaonebot-ci:98'],
            ['image', 'rm', 'formulaonebot-web:old'],
            ['image', 'rm', 'formulaonebot-app:old'],
            ['image', 'rm', 'sha256:dangling'],
        ])

    def test_failed_container_inspection_stops_before_removing_images(self):
        code, removed = self.scenario('container_inspect_failure')
        self.assertNotEqual(code, 0)
        self.assertEqual(removed, [])

    def test_failed_protected_tag_inspection_stops_before_removing_images(self):
        code, removed = self.scenario('tag_inspect_failure')
        self.assertNotEqual(code, 0)
        self.assertEqual(removed, [])

    def test_removal_failure_does_not_prevent_remaining_cleanup(self):
        code, removed = self.scenario('remove_failure')
        self.assertEqual(code, 0)
        self.assertEqual(len(removed), 4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
