"""Send CI results only to the configured administrator, without logging secrets."""
import json
import os
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    reports = Path('/reports')
    totals = dict(tests=0, failures=0, errors=0, skipped=0)
    for path in reports.glob('*.xml'):
        root = ET.parse(path).getroot()
        # Node emits testcases directly under testsuites; pytest nests them.
        # Count individual cases so both layouts work without counting totals twice.
        for case in root.iter('testcase'):
            totals['tests'] += 1
            for key, tag in [('failures', 'failure'), ('errors', 'error'), ('skipped', 'skipped')]:
                totals[key] += int(case.find(tag) is not None)
    result = os.environ.get('CI_RESULT', 'UNKNOWN')
    deployment = 'not_started'
    if (reports / 'deployment.json').exists():
        deployment = json.loads((reports / 'deployment.json').read_text())['status']
    deployment_text = {
        'not_started': 'Приложение не обновлялось.',
        'unchanged': 'Приложение уже использует проверенный образ.',
        'superseded': 'В main появился новый commit. Эта версия не развёртывалась.',
        'deploying': 'Развёртывание прервано; проверь состояние приложения.',
        'deployed': 'Приложение обновлено, проверка запуска успешна.',
        'rolled_back': 'Ошибка развёртывания. Предыдущая версия восстановлена.',
        'rollback_failed': 'Ошибка развёртывания и отката. Требуется вмешательство администратора.',
    }[deployment]
    commit = (reports / 'commit.txt').read_text().strip()[:12] if (reports / 'commit.txt').exists() else 'unknown'
    text = (
        f'F1Hub · Jenkins #{os.environ.get("BUILD_NUMBER", "?")} · {result}\n'
        f'Commit: {commit}\n'
        f'Тестов: {totals["tests"]}; ошибок: {totals["failures"] + totals["errors"]}; '
        f'пропущено: {totals["skipped"]}\n'
        f'Длительность: {os.environ.get("CI_DURATION", "?").replace(" and counting", "")}\n'
        f'{deployment_text}\n{os.environ.get("BUILD_URL", "https://jenkins.f1hub.ru/")}'
    )
    request = urllib.request.Request(
        'https://api.telegram.org/bot' + os.environ['TELEGRAM_BOT_TOKEN'] + '/sendMessage',
        data=json.dumps({'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': text,
                         'disable_web_page_preview': True}).encode(),
        headers={'Content-Type': 'application/json'},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                assert json.load(response)['ok']
            print('CI result delivered to administrator.')
            return
        except (urllib.error.URLError, TimeoutError, AssertionError):
            if attempt < 2:
                time.sleep(3)
    raise SystemExit('Failed to deliver CI notification after 3 attempts.')


if __name__ == '__main__':
    main()
