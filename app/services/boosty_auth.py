"""Server-only Boosty credentials with bounded refresh and durable token rotation."""
from __future__ import annotations

import asyncio
import errno
import json
import math
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx


class BoostyUnavailable(Exception):
    def __init__(self, message, *, code='unavailable'):
        super().__init__(message)
        self.code = code


class BoostyAuth:
    def __init__(self):
        self.lock = asyncio.Lock()
        self._pending = None
        self._pending_revision = None

    def revision(self):
        """Opaque file identity; contains no credential values."""
        try:
            stat = self.path.stat()
            return (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    @asynccontextmanager
    async def exclusive(self):
        """Serialize refresh across service instances, processes and the login utility."""
        async with self.lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
            except OSError as exc:
                raise BoostyUnavailable('Не удалось заблокировать подключение Boosty') from exc
            acquired = False
            try:
                if os.name == 'nt':
                    import msvcrt
                    if os.fstat(descriptor).st_size == 0:
                        os.write(descriptor, b'0')
                    def acquire():
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    def release():
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    def acquire():
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    def release():
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                deadline = time.monotonic() + 30
                while not acquired:
                    try:
                        acquire()
                        acquired = True
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise BoostyUnavailable('Не удалось заблокировать подключение Boosty') from exc
                        if time.monotonic() >= deadline:
                            raise BoostyUnavailable('Подключение Boosty занято. Повторите позже') from exc
                        await asyncio.sleep(0.05)
                yield
            finally:
                try:
                    if acquired:
                        release()
                finally:
                    os.close(descriptor)

    @property
    def path(self):
        default = Path(__file__).resolve().parents[2] / 'data' / 'boosty-auth.json'
        return Path(os.getenv('BOOSTY_AUTH_FILE', str(default)))

    @staticmethod
    def token(value):
        return isinstance(value, str) and bool(re.fullmatch(r'[\x21-\x7e]{1,16384}', value))

    def load(self):
        if self._pending is not None:
            if self.revision() != self._pending_revision:
                # A newly installed owner session supersedes an unsaved old rotation.
                self._pending = None
            else:
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
        self._pending_revision = self.revision()
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
        async with self.exclusive():
            data = self.load()
            if rejected_token is not None and data['access_token'] != rejected_token:
                return data
            if rejected_token is None and (data.get('expires_at') is None
                                          or data['expires_at'] > time.time() + 60):
                return data
            if not data.get('refresh_token') or not data.get('device_id'):
                raise BoostyUnavailable('Подключение Boosty требует обновления владельцем проекта',
                                        code='auth_required')
            response = await client.post('https://api.boosty.to/oauth/token/', data={
                'device_id': data['device_id'], 'device_os': 'web',
                'grant_type': 'refresh_token', 'refresh_token': data['refresh_token'],
            }, headers={'Authorization': 'Bearer ' + data['access_token']})
            if response.status_code in (400, 401, 403):
                raise BoostyUnavailable('Подключение Boosty требует обновления владельцем проекта',
                                        code='auth_required')
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
        response = await self._get_with_retry(client, url, params=params, token=data['access_token'])
        if response.status_code == 401:
            data = await self.renew(client, data['access_token'])
            response = await self._get_with_retry(client, url, params=params, token=data['access_token'])
        return response

    @staticmethod
    async def _get_with_retry(client, url, *, params, token):
        # Only reads are replayed: retrying a refresh POST can lose a rotated token.
        for attempt in range(3):
            try:
                response = await client.get(url, params=params,
                                            headers={'Authorization': 'Bearer ' + token})
            except httpx.TransportError:
                if attempt == 2:
                    raise
            else:
                if response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                    return response
                # Respect long rate limits by returning immediately, without an early retry.
                if response.status_code == 429:
                    try:
                        retry_after = float(response.headers.get('Retry-After', '60'))
                    except ValueError:
                        return response
                    if not math.isfinite(retry_after) or not 0 <= retry_after <= 2:
                        return response
                    await asyncio.sleep(retry_after)
                    continue
            await asyncio.sleep(0.5 * (attempt + 1))
