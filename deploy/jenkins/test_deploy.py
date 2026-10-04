"""Exercise deployment and rollback with a fake Docker CLI; production is untouched."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

FAKE_DOCKER = '''#!/usr/bin/python3
import json,os,pathlib,sys
p=pathlib.Path(os.environ['VALIDATION_DIR']); args=sys.argv[1:]
with (p/'calls.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
mode=os.environ['VALIDATION_MODE']
if args[0]=='inspect': print('sha256:old')
elif args[:2]==['image','inspect']: print('sha256:old' if mode=='unchanged' else 'sha256:new')
elif args[0]=='compose':
 n=int((p/'count').read_text())+1 if (p/'count').exists() else 1
 (p/'count').write_text(str(n))
 if mode=='rollout_failure' and n==1: sys.exit(1)
 if mode=='rollback_failure': sys.exit(1)
elif args[:3]==['exec','formulaonebot-web-1','python']:
 if mode=='backup_failure' and 'src.backup' in args[-1]: sys.exit(1)
 if mode=='public_failure' and 'https://' in args[-1]: sys.exit(1)
'''


class DeploymentTests(unittest.TestCase):
    def scenario(self, mode):
        with tempfile.TemporaryDirectory(prefix='f1hub-ci-validation-') as tmp:
            root = Path(tmp)
            (root / 'reports').mkdir()
            cli = root / 'docker'
            cli.write_text(FAKE_DOCKER)
            cli.chmod(0o700)
            script = Path(__file__).with_name('deploy-verified.sh').read_text()
            script = script.replace('cd /root/FormulaOneBot', 'cd "$VALIDATION_DIR"')
            script = script.replace('/reports/deployment.json', '"$VALIDATION_DIR/reports/deployment.json"')
            env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                       VALIDATION_DIR=str(root), VALIDATION_MODE=mode, APP_IMAGE='ci:test', BUILD_NUMBER='test')
            process = subprocess.run(['sh'], input=script, text=True, capture_output=True, env=env)
            status_path = root / 'reports/deployment.json'
            status = json.loads(status_path.read_text())['status'] if status_path.exists() else None
            calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
            return process.returncode, status, calls

    def test_success_promotes_the_tested_image(self):
        code, status, calls = self.scenario('success')
        self.assertEqual((code, status), (0, 'deployed'))
        self.assertIn(['tag', 'sha256:new', 'formulaonebot-app:latest'], calls)
        self.assertIn(['tag', 'sha256:old', 'formulaonebot-rollback:previous'], calls)

    def test_failed_rollout_restores_previous_image(self):
        code, status, calls = self.scenario('rollout_failure')
        self.assertNotEqual(code, 0)
        self.assertEqual(status, 'rolled_back')
        self.assertIn(['tag', 'sha256:old', 'formulaonebot-app:latest'], calls)

    def test_failed_public_health_check_also_rolls_back(self):
        code, status, calls = self.scenario('public_failure')
        self.assertNotEqual(code, 0)
        self.assertEqual(status, 'rolled_back')
        self.assertIn(['tag', 'sha256:old', 'formulaonebot-app:latest'], calls)

    def test_backup_failure_never_changes_production_tag(self):
        code, status, calls = self.scenario('backup_failure')
        self.assertNotEqual(code, 0)
        self.assertIsNone(status)
        self.assertFalse(any(call[0] == 'tag' for call in calls))

    def test_rollback_failure_is_explicit(self):
        code, status, _ = self.scenario('rollback_failure')
        self.assertNotEqual(code, 0)
        self.assertEqual(status, 'rollback_failed')

    def test_unchanged_image_does_not_restart_application(self):
        code, status, calls = self.scenario('unchanged')
        self.assertEqual((code, status), (0, 'unchanged'))
        self.assertFalse(any(call[0] == 'compose' for call in calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
