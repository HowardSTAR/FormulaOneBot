"""Server-only Boosty credentials with bounded refresh and durable token rotation."""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path

import httpx


class BoostyUnavailable(Exception):
    pass


class BoostyAuth:
    def __init__(self):
        self.lock = asyncio.Lock()
        self._pending = None

    @property
    def path(self):
        default = Path(__file__).resolve().parents[2] / 'data' / 'boosty-auth.json'
        return Path(os.getenv('BOOSTY_AUTH_FILE', str(default)))

    @staticmethod
    def token(value):
        return isinstance(value, str) and bool(re.fullmatch(r'[\x21-\x7e]{1,16384}', value))

    def load(self):
        if self._pending is not None:
            self.save(self._pending)
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding='utf-8-sig'))
                if not isinstance(data, dict) or not self.token(data.get('access_token')):
                    raise BoostyUnavailable('Неверный формат подключения Boosty')
                for key in ('refresh_token', 'device_id'):
                    if data.get(key) is not None and not self.token(data[key]):
                        raise BoostyUnavailable('Неверный формат подключения Boosty')
                expiry = data.get('expires_at')
                if expiry is not None and (type(expiry) not in (int, float) or not math.isfinite(expiry)):
                    raise BoostyUnavailable('Неверный срок авторизации Boosty')
                return data
            access = os.getenv('BOOSTY_ACCESS_TOKEN', '').strip()
            if not access:
                default = Path(__file__).resolve().parents[2] / 'secrets' / 'boosty-access-token.txt'
                path = Path(os.getenv('BOOSTY_ACCESS_TOKEN_FILE', str(default)))
                access = path.read_text(encoding='utf-8-sig').strip() if path.exists() else ''
            if access and not self.token(access):
                raise BoostyUnavailable('Неверный формат подключения Boosty')
            return {'access_token': access}
        except (OSError, ValueError) as exc:
            raise BoostyUnavailable('Не удалось прочитать подключение Boosty') from exc

    def save(self, data):
        # Retain a rotated pair in memory until it has been durably stored.
        self._pending = data
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.boosty-auth-', delete=False) as handle:
                temporary = Path(handle.name)
                temporary.chmod(0o600)
                json.dump(data, handle)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
            self._pending = None
        except OSError as exc:
            raise BoostyUnavailable('Не удалось сохранить обновлённое подключение Boosty') from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    async def renew(self, client, rejected_token=None):
        async with self.lock:
            data = self.load()
            if rejected_token is not None and data['access_token'] != rejected_token:
                return data
            if rejected_token is None and (data.get('expires_at') is None
                                          or data['expires_at'] > time.time() + 60):
                return data
            if not data.get('refresh_token') or not data.get('device_id'):
                raise BoostyUnavailable('Подключение Boosty требует обновления владельцем проекта')
            response = await client.post('https://api.boosty.to/oauth/token/', data={
                'device_id': data['device_id'], 'device_os': 'web',
                'grant_type': 'refresh_token', 'refresh_token': data['refresh_token'],
            }, headers={'Authorization': 'Bearer ' + data['access_token']})
            if response.status_code in (400, 401, 403):
                raise BoostyUnavailable('Подключение Boosty требует обновления владельцем проекта')
            response.raise_for_status()
            payload = response.json()
            if (not isinstance(payload, dict) or not self.token(payload.get('access_token'))
                    or not self.token(payload.get('refresh_token'))):
                raise BoostyUnavailable('Неизвестный ответ обновления подключения Boosty')
            lifetime = payload.get('expires_in')
            if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or lifetime <= 0:
                raise BoostyUnavailable('Неизвестный срок обновления подключения Boosty')
            updated = {**data, 'access_token': payload['access_token'],
                       'refresh_token': payload['refresh_token'], 'expires_at': time.time() + lifetime}
            self.save(updated)
            return updated

    async def get(self, client, url, *, params):
        data = self.load()
        if not data['access_token']:
            raise BoostyUnavailable('Проверка Boosty ещё не настроена')
        if (data.get('expires_at') is not None and data['expires_at'] <= time.time() + 60
                and data.get('refresh_token') and data.get('device_id')):
            data = await self.renew(client)
        response = await client.get(url, params=params, headers={'Authorization': 'Bearer ' + data['access_token']})
        if response.status_code == 401:
            data = await self.renew(client, data['access_token'])
            response = await client.get(url, params=params, headers={'Authorization': 'Bearer ' + data['access_token']})
        return response
