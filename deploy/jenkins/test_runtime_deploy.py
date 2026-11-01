"""Real Git history + fake Docker verify which commits can restart production."""
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from cli_fixtures import cli_environment, shell_path, write_fake_cli

FAKE_DOCKER = '''#!/usr/bin/python3
import json,os,pathlib,sys
p=pathlib.Path(os.environ['VALIDATION_DIR'])
args=sys.argv[1:]
with (p/'calls.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
if args[0]=='inspect':
 print(os.environ['VALIDATION_VERSION'] if 'version' in args[-1] else os.environ.get('VALIDATION_HEALTH','healthy'+chr(10)+'healthy'+chr(10)+'healthy'+chr(10)+'healthy'))
if args[-2:]==['nginx','-t'] and os.environ.get('VALIDATION_FAIL_PROXY')=='1': sys.exit(1)
'''


@unittest.skipUnless(shutil.which('git'), 'Real Git is required for deployment history tests')
class RuntimeDeploymentTests(unittest.TestCase):
    def scenario(self, changed=None, version=None, proxy_failure=False, unhealthy=False):
        with tempfile.TemporaryDirectory(prefix='f1hub-runtime-deploy-') as tmp:
            root=Path(tmp)
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
            git('init','-q')
            (root/'README.md').write_text('initial\n')
            git('add','.')
            git('-c','user.name=CI','-c','user.email=ci@example.test','commit','-qm','initial')
            current=git('rev-parse','--short=12','HEAD')
            if changed:
                file=root/changed
                file.parent.mkdir(parents=True,exist_ok=True)
                file.write_text('changed\n')
                git('add','.')
                git('-c','user.name=CI','-c','user.email=ci@example.test','commit','-qm','change')
            (root/'reports').mkdir()
            write_fake_cli(root/'docker',FAKE_DOCKER)
            env=cli_environment(root,WORKSPACE=str(root),CI_SCRIPTS=str(root/'trusted'),
                BUILD_NUMBER='test',APP_IMAGE='ci:test',VALIDATION_DIR=str(root),
                VALIDATION_VERSION=current if version is None else version,
                VALIDATION_FAIL_PROXY='1' if proxy_failure else '0',
                VALIDATION_HEALTH='unhealthy' if unhealthy else 'healthy\nhealthy\nhealthy\nhealthy')
            result=subprocess.run([shell_path(),str(Path(__file__).with_name('run-ci.sh').resolve()),'deploy'],env=env,text=True,capture_output=True,timeout=30)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            report=root/'reports/deployment.json'
            return result.returncode,calls,json.loads(report.read_text()) if report.exists() else None

    def test_same_commit_and_proxy_or_docs_changes_keep_app_running(self):
        for changed in [None,'nginx.conf','docs/deployment.md','deploy/jenkins/run-ci.sh']:
            with self.subTest(changed=changed):
                code,calls,report=self.scenario(changed)
                self.assertEqual(code,0)
                self.assertEqual(report,{'status':'unchanged'})
                self.assertNotIn('run',[call[0] for call in calls])
                self.assertIn(['exec','formulaonebot-nginx-1','nginx','-t'],calls)
                self.assertIn(['exec','formulaonebot-nginx-1','nginx','-s','reload'],calls)

    def test_app_image_assets_and_compose_changes_use_full_deployment(self):
        for changed in ['app/api.py','front/src/App.tsx','race-game/src/main.ts','legacy/public-frontend.tar.gz','app-assets.zip','Dockerfile','requirements.txt','docker-compose-build.yml','.dockerignore','scripts/pack_assets.py','THIRD_PARTY_NOTICES.md','ASSET_LICENSES.md']:
            with self.subTest(changed=changed):
                code,calls,report=self.scenario(changed)
                self.assertEqual(code,0)
                self.assertTrue(any(call[0]=='run' for call in calls))
                self.assertIsNone(report)

    def test_unknown_versions_never_skip_deployment(self):
        for version in ['latest','','123456789abc']:
            with self.subTest(version=version):
                code,calls,_=self.scenario('nginx.conf',version=version)
                self.assertEqual(code,0)
                self.assertTrue(any(call[0]=='run' for call in calls))

    def test_unhealthy_services_never_skip_recovery(self):
        code,calls,_=self.scenario('nginx.conf',unhealthy=True)
        self.assertEqual(code,0)
        self.assertTrue(any(call[0]=='run' for call in calls))

    def test_invalid_proxy_configuration_fails_without_restarting_apps(self):
        code,calls,report=self.scenario('nginx.conf',proxy_failure=True)
        self.assertNotEqual(code,0)
        self.assertIsNone(report)
        self.assertFalse(any(call[0]=='run' or call[-1]=='reload' for call in calls))


if __name__=='__main__': unittest.main(verbosity=2)
