"""Interactive owner login in an isolated browser; no manual token copying.

The optional SSH configuration lives in ignored secrets/boosty-connect.json.
Passwords, cookies and tokens are never accepted as command-line values or logged.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.boosty_auth import BoostyAuth, BoostyUnavailable  # noqa: E402
from scripts.configure_boosty_auth import normalize  # noqa: E402


class ConnectionError(Exception):
    """Safe message suitable for displaying to the owner."""


def session_from_cookies(cookies):
    values = {item['name']: item['value'] for item in cookies
              if item.get('domain', '').lstrip('.') == 'boosty.to'
              and item.get('name') in ('auth', '_clientId')}
    if not values.get('auth') or not values.get('_clientId'):
        return None
    try:
        return normalize({'auth': values['auth'], '_clientId': values['_clientId']})
    except (ValueError, TypeError):
        return None


async def capture_session(playwright, *, channel='msedge', timeout=600):
    browser = await playwright.chromium.launch(channel=channel, headless=False)
    try:
        context = await browser.new_context(locale='ru-RU')
        page = await context.new_page()
        await page.goto('https://boosty.to/', wait_until='domcontentloaded', timeout=60000)
        print('Войдите в аккаунт владельца Boosty в открывшемся окне. Токены копировать не нужно.', flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not browser.is_connected() or not context.pages:
                raise ConnectionError('Окно входа закрыто. Подключение не изменено.')
            data = session_from_cookies(await context.cookies('https://boosty.to/'))
            if data:
                # Stop the browser before server-side refresh can compete with it.
                return data
            await asyncio.sleep(0.5)
        raise ConnectionError('Время ожидания входа истекло. Запустите подключение снова.')
    finally:
        await browser.close()


def read_config(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('config')
        if not isinstance(data.get('host'), str) or not re.fullmatch(r'[A-Za-z0-9.:-]+', data['host']):
            raise ValueError('host')
        for field, default in [('username', 'root'), ('container', 'formulaonebot-web-1')]:
            if not isinstance(data.get(field, default), str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', data.get(field, default)):
                raise ValueError(field)
        if type(data.get('port', 22)) is not int or not 1 <= data.get('port', 22) <= 65535:
            raise ValueError('port')
        return data
    except (OSError, ValueError, TypeError) as exc:
        raise ConnectionError('Не удалось прочитать настройки сервера Boosty.') from exc


def install_remote(data, config):
    import paramiko
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    if config.get('known_hosts'):
        client.load_host_keys(str(Path(config['known_hosts']).expanduser()))
    # Unknown or changed host keys are rejected; no trust-on-first-use workaround.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    password = None
    try:
        if config.get('password_file'):
            password = Path(config['password_file']).expanduser().read_text(encoding='utf-8-sig').strip()
        client.connect(config['host'], port=config.get('port', 22), username=config.get('username', 'root'),
                       password=password, key_filename=config.get('key_file'),
                       look_for_keys=not bool(password), allow_agent=not bool(password),
                       timeout=15, auth_timeout=15, banner_timeout=15)
        password = None
        source = (ROOT / 'scripts/install_boosty_connection.py').read_text(encoding='utf-8')
        command = 'docker exec -i ' + shlex.quote(config.get('container', 'formulaonebot-web-1'))
        command += ' python -c ' + shlex.quote(source)
        stdin, stdout, stderr = client.exec_command(command, timeout=180)
        stdin.write(json.dumps(data))
        stdin.channel.shutdown_write()
        output = stdout.read(65537)
        stderr.read(65537)  # Never display upstream bodies or credential-bearing tracebacks.
        code = stdout.channel.recv_exit_status()
        try:
            result = json.loads(output)
        except ValueError as exc:
            raise ConnectionError('Сервер не подтвердил подключение. Локальный сеанс сохранён для повторной попытки.') from exc
        if code or not isinstance(result, dict) or result.get('installed') is not True:
            if isinstance(result, dict) and result.get('error_code') == 'auth_required':
                raise ConnectionError('Boosty отклонил сеанс владельца. Выполните новый вход; подключение сервера не заменено.')
            raise ConnectionError('Не удалось проверить и установить сеанс. Подключение сервера не заменено; повторите с --retry.')
        return {'installed': True, 'synced': result.get('synced') is True}
    finally:
        password = None
        client.close()


async def connect(args):
    config = read_config(args.config) if args.config else None
    # Check dependencies before opening a browser or changing any session.
    if config:
        try:
            import paramiko  # noqa: F401
        except ImportError as exc:
            raise ConnectionError('Установите requirements-boosty-connect.txt в локальное Python-окружение.') from exc
    pending = ROOT / 'secrets' / 'boosty-pending-auth.json'
    previous_path = os.environ.get('BOOSTY_AUTH_FILE')
    try:
        os.environ['BOOSTY_AUTH_FILE'] = str(pending)
        if args.retry:
            data = normalize(BoostyAuth().load())
        else:
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise ConnectionError('Установите requirements-boosty-connect.txt в локальное Python-окружение.') from exc
            async with async_playwright() as playwright:
                data = await capture_session(playwright, channel=args.browser, timeout=args.timeout)
            BoostyAuth().save(data)
        print('Отдельный сеанс получен. Проверяем подключение…', flush=True)
        if config:
            result = await asyncio.to_thread(install_remote, data, config)
        else:
            from scripts.install_boosty_connection import install
            os.environ['BOOSTY_AUTH_FILE'] = str(args.output.resolve())
            result = await install(data)
        if result['installed']:
            pending.unlink(missing_ok=True)
            print('Boosty подключён. Обновление токенов и проверка подписок выполняются сервером.', flush=True)
            if not result['synced']:
                print('Первая синхронизация ожидает повторной попытки фонового сервиса.', flush=True)
        return 0
    finally:
        if previous_path is None:
            os.environ.pop('BOOSTY_AUTH_FILE', None)
        else:
            os.environ['BOOSTY_AUTH_FILE'] = previous_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='SSH settings file; defaults to secrets/boosty-connect.json if present')
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'boosty-auth.json')
    parser.add_argument('--browser', choices=['msedge', 'chrome', 'chromium'], default='msedge')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--retry', action='store_true', help='Retry transfer of the last captured session without another login')
    args = parser.parse_args()
    default_config = ROOT / 'secrets' / 'boosty-connect.json'
    if args.config is None and default_config.exists():
        args.config = default_config
    if not 30 <= args.timeout <= 3600:
        parser.error('timeout must be between 30 and 3600 seconds')
    try:
        return asyncio.run(connect(args))
    except (ConnectionError, BoostyUnavailable) as exc:
        print(str(exc), file=sys.stderr)
    except KeyboardInterrupt:
        print('Подключение отменено.', file=sys.stderr)
    except Exception:
        print('Не удалось завершить подключение. Значения авторизации скрыты. Повторите попытку.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
