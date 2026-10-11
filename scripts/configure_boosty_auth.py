"""Import owner-provided Boosty cookies into the server's durable auth file.

No credential values are accepted as command-line arguments or printed.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.boosty_auth import BoostyAuth, BoostyUnavailable  # noqa: E402


def normalize(payload):
    if not isinstance(payload, dict):
        raise ValueError('Ожидался JSON-объект подключения Boosty')
    raw = payload.get('auth', payload)
    if isinstance(raw, str):
        raw = json.loads(unquote(raw))
    if not isinstance(raw, dict):
        raise ValueError('Неверный формат auth')
    result = {
        'access_token': raw.get('access_token', raw.get('accessToken')),
        'refresh_token': raw.get('refresh_token', raw.get('refreshToken')),
        'device_id': payload.get('device_id', payload.get('_clientId')),
    }
    if not all(BoostyAuth.token(value) for value in result.values()):
        raise ValueError('Нужны access token, refresh token и идентификатор устройства')
    expiry = raw.get('expires_at', raw.get('expiresAt'))
    if expiry is not None:
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry < 0:
            raise ValueError('Неверный срок авторизации Boosty')
        result['expires_at'] = expiry / 1000 if expiry > 1e12 else expiry
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = normalize(json.loads(args.input.read_text(encoding='utf-8-sig')))
        os.environ['BOOSTY_AUTH_FILE'] = str(args.output.resolve())
        BoostyAuth().save(data)
    except (OSError, ValueError, BoostyUnavailable):
        print('Не удалось импортировать подключение. Проверьте формат файла и права доступа.', file=sys.stderr)
        return 1
    print('Подключение сохранено. Значения авторизации скрыты.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
