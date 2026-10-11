"""Rotated credentials survive restarts; failures cannot erase paid access."""
import asyncio
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest

from app.services.boosty_auth import BoostyAuth, BoostyUnavailable
from scripts.configure_boosty_auth import normalize


@pytest.fixture
def auth(tmp_path, monkeypatch):
    monkeypatch.setenv('BOOSTY_AUTH_FILE', str(tmp_path / 'auth.json'))
    monkeypatch.setenv('BOOSTY_ACCESS_TOKEN', 'stale-environment-token')
    result = BoostyAuth()
    result.save({'access_token': 'old-access', 'refresh_token': 'old-refresh',
                 'device_id': 'test-device', 'expires_at': time.time() + 3600})
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize('proactive', [False, True])
async def test_refresh_persists_rotation_and_uses_file_before_environment(auth, proactive):
    if proactive:
        auth.save({**auth.load(), 'expires_at': time.time() - 1})
    calls = []
    def handle(request):
        calls.append(request)
        if request.method == 'POST':
            assert str(request.url) == 'https://api.boosty.to/oauth/token/'
            assert parse_qs(request.content.decode()) == {
                'device_id': ['test-device'], 'device_os': ['web'],
                'grant_type': ['refresh_token'], 'refresh_token': ['old-refresh']}
            return httpx.Response(200, json={'access_token': 'new-access',
                'refresh_token': 'new-refresh', 'expires_in': 3600})
        return httpx.Response(200 if request.headers['authorization'] == 'Bearer new-access' else 401)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await auth.get(client, 'https://api.boosty.to/v1/blog/turbotears/subscribers', params={})
    assert result.status_code == 200
    assert [request.method for request in calls] == (['POST', 'GET'] if proactive else ['GET', 'POST', 'GET'])
    restarted = BoostyAuth().load()
    assert restarted['access_token'] == 'new-access'
    assert restarted['refresh_token'] == 'new-refresh'
    assert restarted['expires_at'] > time.time() + 3500


@pytest.mark.asyncio
async def test_concurrent_401_refreshes_once_and_retries_once(auth):
    requests = []
    async def handle(request):
        requests.append(request.method)
        if request.method == 'POST':
            await asyncio.sleep(0)
            return httpx.Response(200, json={'access_token': 'new-access',
                'refresh_token': 'new-refresh', 'expires_in': 3600})
        return httpx.Response(401)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        results = await asyncio.gather(*[auth.get(client, 'https://api.boosty.to/test', params={}) for _ in range(2)])
    assert all(result.status_code == 401 for result in results)
    assert requests.count('POST') == 1
    assert requests.count('GET') == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [400, 401, 403])
async def test_refresh_rejection_keeps_file_and_hides_upstream_body(auth, status):
    before = auth.path.read_bytes()
    def handle(request):
        return httpx.Response(status if request.method == 'POST' else 401,
                              text='sensitive upstream body old-refresh')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(BoostyUnavailable) as error:
            await auth.get(client, 'https://api.boosty.to/test', params={})
    assert 'old-refresh' not in str(error.value)
    assert 'sensitive' not in str(error.value)
    assert auth.path.read_bytes() == before


def test_failed_write_retains_rotated_pair_for_retry(auth, monkeypatch):
    original = auth.path.__class__.replace
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(auth.path.__class__, 'replace', fail)
    rotated = {**auth.load(), 'access_token': 'rotated-access', 'refresh_token': 'rotated-refresh'}
    with pytest.raises(BoostyUnavailable):
        auth.save(rotated)
    monkeypatch.setattr(auth.path.__class__, 'replace', original)
    assert auth.load() == rotated
    assert BoostyAuth().load() == rotated


@pytest.mark.parametrize('value', [[], {'access_token': 'bad\nheader'},
    {'access_token': 'valid', 'refresh_token': ''}, {'access_token': 'valid', 'expires_at': float('nan')}])
def test_malformed_file_does_not_fall_back_to_old_environment(auth, value):
    auth.path.write_text(json.dumps(value))
    with pytest.raises(BoostyUnavailable):
        auth.load()


def test_cookie_import_normalizes_browser_expiry_and_ignores_extra_data():
    from urllib.parse import quote
    browser = {'accessToken': 'access', 'refreshToken': 'refresh',
               'expiresAt': 1791800000000, 'unrelated': 'excluded'}
    result = normalize({'auth': quote(json.dumps(browser)), 'device_id': 'device'})
    assert result == {'access_token': 'access', 'refresh_token': 'refresh',
                      'device_id': 'device', 'expires_at': 1791800000}
    assert normalize(result) == result


@pytest.mark.parametrize('payload', [None, {}, {'auth': '{}', 'device_id': 'device'},
    {'access_token': 'access', 'refresh_token': 'refresh', 'device_id': 'device', 'expires_at': True}])
def test_cookie_import_rejects_incomplete_credentials(payload):
    with pytest.raises(ValueError):
        normalize(payload)
