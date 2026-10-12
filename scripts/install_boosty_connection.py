"""Read an owner session from stdin, validate it, install atomically and sync rights.

Run in the web container. All output is an allowlisted JSON summary, never credentials.
The desktop connector sends this source over SSH, so it also works with an older image.
"""
import asyncio
import json
import math
import os
import sys
import tempfile
from pathlib import Path


async def install(data):
    from app.db import db
    from app.services.boosty_auth import BoostyAuth
    from app.services.boosty_service import BoostyService
    # The runtime image contains app/, but not the desktop scripts/ package.
    # Accept only the normalized fields sent by the connector.
    if not isinstance(data, dict) or not all(BoostyAuth.token(data.get(key))
                                            for key in ('access_token', 'refresh_token', 'device_id')):
        raise ValueError('invalid normalized session')
    expiry = data.get('expires_at')
    if expiry is not None and (type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry < 0):
        raise ValueError('invalid expiry')
    data = {key: data[key] for key in ('access_token', 'refresh_token', 'device_id', 'expires_at') if key in data}
    target = BoostyAuth().path
    target.parent.mkdir(parents=True, exist_ok=True)
    old_environment = os.environ.get('BOOSTY_AUTH_FILE')
    try:
        with tempfile.TemporaryDirectory(prefix='.boosty-connect-', dir=target.parent) as folder:
            os.environ['BOOSTY_AUTH_FILE'] = str(Path(folder) / 'auth.json')
            candidate = BoostyService(None)
            candidate.auth.save(data)
            rows = await candidate.fetch_subscribers()
            # Validate every entry before replacing the working owner session.
            import time
            emails = set()
            for row in rows:
                candidate.membership(row, time.time())
                email = row['email'].strip().casefold()
                if email in emails:
                    raise ValueError('ambiguous subscriber identity')
                emails.add(email)
            data = candidate.auth.load()  # Includes any tokens rotated during validation.
            os.environ['BOOSTY_AUTH_FILE'] = str(target)
            auth = BoostyAuth()
            if hasattr(auth, 'exclusive'):
                async with auth.exclusive():
                    auth.save(data)
            else:
                # Compatibility with the already deployed Linux image during rollout.
                import fcntl
                descriptor = os.open(str(target) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                    auth.save(data)
                finally:
                    os.close(descriptor)
    finally:
        if old_environment is None:
            os.environ.pop('BOOSTY_AUTH_FILE', None)
        else:
            os.environ['BOOSTY_AUTH_FILE'] = old_environment

    result = {'installed': True, 'synced': False, 'subscribers': len(rows)}
    try:
        await db.connect()
        service = BoostyService(db)
        await service.sync()
        result['synced'] = True
    except Exception:
        # Installation succeeded: the regular worker can retry the sync.
        result['error_code'] = 'sync_pending'
    finally:
        await db.close()
    return result


def main():
    try:
        # Bound stdin so a malformed invocation cannot exhaust container memory.
        raw = sys.stdin.read(65537)
        if len(raw) > 65536:
            raise ValueError('oversized session')
        result = asyncio.run(install(json.loads(raw)))
    except Exception as exc:
        result = {'installed': False, 'synced': False,
                  'error_code': getattr(exc, 'code', 'connection_failed'),
                  'error_type': type(exc).__name__}
        print(json.dumps(result))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
