"""Run as root on the existing F1Hub Docker host, using an uploaded source bundle."""
import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def run(*args):
    subprocess.run(args, check=True)


def prepare():
    bundle = json.loads(Path('/root/f1hub-ci-package.json').read_text())
    target = Path('/opt/f1hub-ci')
    target.mkdir(exist_ok=True)
    backup = Path('/root/f1hub-ci-backups') / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    for path in ['/root/FormulaOneBot/nginx.conf', '/opt/formulaonebot/deploy/jenkins/docker-compose.yml']:
        shutil.copy2(path, backup / (Path(path).parent.name + '-' + Path(path).name))
    home = '/var/lib/docker/volumes/f1hub_jenkins_home/_data'
    run('tar', '-czf', str(backup / 'jenkins-home.tar.gz'), '-C', home, '.')
    os.chmod(backup / 'jenkins-home.tar.gz', 0o600)
    for name, content in bundle.items():
        assert '/' not in name and '\\' not in name
        (target / name).write_text(content, encoding='utf-8')
    gid = Path('/var/run/docker.sock').stat().st_gid
    (target / '.env').write_text(f'DOCKER_GID={gid}\nTZ=Europe/Moscow\n')
    workspace = Path('/srv/jenkins-workspace')
    workspace.mkdir(exist_ok=True)
    os.chown(workspace, 1000, 1000)
    private = Path('/root/f1hub-ci-bootstrap')
    private.mkdir(exist_ok=True, mode=0o750)
    os.chown(private, 0, 1000)
    env = json.loads(subprocess.check_output(['docker', 'inspect', 'formulaonebot-web-1']))[0]['Config']['Env']
    env = dict(item.split('=', 1) for item in env)
    admins = [value.strip() for value in env['ADMIN_IDS'].split(',') if value.strip()]
    assert len(admins) == 1, 'Select the recipient before proceeding if multiple admins exist.'
    values = {'username': 'f1hub-admin', 'password': secrets.token_urlsafe(24),
              'bot_token': env['BOT_TOKEN'], 'chat_id': admins[0],
              'webhook_secret': secrets.token_hex(32)}
    (private / 'secrets.json').write_text(json.dumps(values))
    os.chown(private / 'secrets.json', 0, 1000)
    os.chmod(private / 'secrets.json', 0o640)
    credentials = Path('/root/f1hub-ci')
    credentials.mkdir(exist_ok=True, mode=0o700)
    (credentials / 'login.txt').write_text('URL: https://jenkins.f1hub.ru/\nLogin: ' + values['username'] + '\nPassword: ' + values['password'] + '\n')
    os.chmod(credentials / 'login.txt', 0o600)
    (credentials / 'webhook-secret.txt').write_text(values['webhook_secret'])
    os.chmod(credentials / 'webhook-secret.txt', 0o600)
    public_args = {
        'VITE_LEGAL_OPERATOR_NAME': env.get('LEGAL_OPERATOR_NAME', ''),
        'VITE_LEGAL_OPERATOR_ADDRESS': env.get('LEGAL_OPERATOR_ADDRESS', ''),
        'VITE_LEGAL_CONTACT_EMAIL': env.get('LEGAL_CONTACT_EMAIL', ''),
        'VITE_DATA_STORAGE_LOCATION': env.get('DATA_STORAGE_LOCATION', ''),
    }
    # The authoritative public legal settings live in the production .env.
    for line in Path('/root/FormulaOneBot/.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            if 'VITE_' + key.strip() in public_args:
                public_args['VITE_' + key.strip()] = value.strip().strip('"').strip("'")
    (target / 'build.env').write_text(''.join(f'{k}={v}\n' for k, v in public_args.items()))
    # Give this CI builder an explicit memory/CPU limit and run one build task at a time.
    (target / 'buildkitd.toml').write_text('[worker.oci]\n  max-parallelism = 1\n  gc = true\n  gckeepstorage = 1500\n')
    run('docker', 'builder', 'prune', '--force', '--filter', 'until=168h', '--keep-storage', '1GB')
    print('Prepared CI configuration; protected backup:', backup)


def activate():
    target = Path('/opt/f1hub-ci')
    run('docker', 'compose', '--project-directory', str(target), '-f', str(target / 'docker-compose.yml'), 'stop', 'jenkins')
    home = Path('/var/lib/docker/volumes/f1hub_jenkins_home/_data')
    tree = ET.parse(home / 'config.xml')
    node = tree.getroot().find('workspaceDir')
    if node is None:
        node = ET.SubElement(tree.getroot(), 'workspaceDir')
    node.text = '/srv/jenkins-workspace/${ITEM_FULL_NAME}'
    tree.write(home / 'config.xml', encoding='utf-8', xml_declaration=True)
    os.chown(home / 'config.xml', 1000, 1000)
    init = home / 'init.groovy.d'
    init.mkdir(exist_ok=True)
    shutil.copy2(target / 'bootstrap.groovy', init / 'f1hub-ci.groovy')
    os.chown(init, 1000, 1000)
    os.chown(init / 'f1hub-ci.groovy', 1000, 1000)
    run('docker', 'compose', '--project-directory', str(target), '-f', str(target / 'docker-compose.yml'), 'up', '-d', '--no-build', 'jenkins')
    print('Jenkins activation started; production application was not restarted.')


if __name__ == '__main__':
    {'prepare': prepare, 'activate': activate}[sys.argv[1]]()
