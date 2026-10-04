"""Temporary root-only bootstrap client. Its API token is revoked after validation."""
import base64
import json
from pathlib import Path
import sys
import urllib.request
import urllib.parse
import urllib.error

root = Path('/root/f1hub-ci')
api_path = root / 'api.json'
if not api_path.exists():
    source = Path('/var/lib/docker/volumes/f1hub_jenkins_home/_data/ci-bootstrap-api.json')
    api_path.write_bytes(source.read_bytes())
    api_path.chmod(0o600)
values = json.loads(api_path.read_text())
authorization = base64.b64encode((values['username'] + ':' + values['token']).encode()).decode()


def request(path, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request('http://127.0.0.1:8080/' + path, data=body,
                                 headers={'Authorization': 'Basic ' + authorization})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read().decode()


command = sys.argv[1]
if command == 'validate':
    print(request('pipeline-model-converter/validate', {'jenkinsfile': Path('/opt/f1hub-ci/Jenkinsfile').read_text()}))
elif command == 'build':
    print(request('job/F1Hub-main/build', {}))
    print('Control build queued.')
elif command == 'status':
    job = json.loads(request('job/F1Hub-main/api/json?tree=name,lastBuild[number,result,building,url],builds[number,result],healthReport[description]'))
    print(json.dumps(job))
    print(request('queue/api/json?tree=items[id,why,task[name]]'))
elif command == 'log':
    print(request('job/F1Hub-main/lastBuild/consoleText')[-int(sys.argv[2] if len(sys.argv) > 2 else '5000'):])
elif command == 'script':
    print(request('scriptText', {'script': Path(sys.argv[2]).read_text()}))
elif command == 'finalize':
    home = Path('/var/lib/docker/volumes/f1hub_jenkins_home/_data')
    script = 'import hudson.model.User\nimport jenkins.security.ApiTokenProperty\n' + \
             'def u=User.getById(' + json.dumps(values['username']) + ',false)\n' + \
             'u.getProperty(ApiTokenProperty.class).tokenStore.revokeToken(' + json.dumps(values['uuid']) + ')\nu.save()\nprintln("Temporary setup token revoked.")'
    print(request('scriptText', {'script': script}))
    for file in [api_path, home / 'ci-bootstrap-api.json', home / 'init.groovy.d/f1hub-ci.groovy',
                 Path('/root/f1hub-ci-bootstrap/secrets.json')]:
        file.unlink(missing_ok=True)
else:
    raise SystemExit('Unknown bootstrap command')
