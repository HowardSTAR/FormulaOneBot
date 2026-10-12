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
@pytest.mark.parametrize('proactive', [False, True])
async def test_separate_auth_instances_share_one_refresh(auth, proactive):
    if proactive:
        auth.save({**auth.load(), 'expires_at': time.time() - 1})
    posts = []
    async def handle(request):
        if request.method == 'POST':
            posts.append(request)
            await asyncio.sleep(0.1)
            return httpx.Response(200, json={'access_token': 'new-access',
                'refresh_token': 'new-refresh', 'expires_in': 3600})
        return httpx.Response(200 if request.headers['authorization'] == 'Bearer new-access' else 401)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        responses = await asyncio.gather(*[
            instance.get(client, 'https://api.boosty.to/test', params={})
            for instance in (auth, BoostyAuth())])
    assert [response.status_code for response in responses] == [200, 200]
    assert len(posts) == 1
    assert BoostyAuth().load()['refresh_token'] == 'new-refresh'


@pytest.mark.asyncio
async def test_cancelled_refresh_releases_file_lock(auth):
    entered = asyncio.Event()
    async def hold():
        async with auth.exclusive():
            entered.set()
            await asyncio.Future()
    task = asyncio.create_task(hold())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(1):
        async with BoostyAuth().exclusive():
            pass


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
    assert error.value.code == 'auth_required'
    assert auth.path.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['connection', 502, 503, 504, 500])
async def test_transient_read_failure_recovers_without_rotating_tokens(auth, monkeypatch, failure):
    calls = []
    delays = []
    async def sleep(delay):
        delays.append(delay)
    monkeypatch.setattr(asyncio, 'sleep', sleep)
    def handle(request):
        calls.append(request.method)
        if len(calls) == 1:
            if failure == 'connection':
                raise httpx.ConnectError('offline', request=request)
            return httpx.Response(failure)
        return httpx.Response(200)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        response = await auth.get(client, 'https://api.boosty.to/test', params={})
    assert response.status_code == 200
    assert calls == ['GET', 'GET'] and delays == [0.5]
    assert auth.load()['access_token'] == 'old-access'


@pytest.mark.asyncio
@pytest.mark.parametrize('status,headers,expected_calls', [
    (503, {}, 3), (403, {}, 1), (429, {}, 1),
    (429, {'Retry-After': '60'}, 1), (429, {'Retry-After': 'invalid'}, 1),
    (429, {'Retry-After': '0'}, 3),
])
async def test_read_retries_are_bounded_and_respect_rate_limits(auth, monkeypatch, status, headers, expected_calls):
    calls = []
    async def sleep(delay):
        pass
    monkeypatch.setattr(asyncio, 'sleep', sleep)
    def handle(request):
        calls.append(request.method)
        return httpx.Response(status, headers=headers)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        response = await auth.get(client, 'https://api.boosty.to/test', params={})
    assert response.status_code == status
    assert calls == ['GET'] * expected_calls


@pytest.mark.asyncio
async def test_refresh_transport_failure_is_never_replayed(auth):
    calls = []
    def handle(request):
        calls.append(request.method)
        if request.method == 'POST':
            raise httpx.ReadTimeout('response lost', request=request)
        return httpx.Response(401)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(httpx.ReadTimeout):
            await auth.get(client, 'https://api.boosty.to/test', params={})
    assert calls == ['GET', 'POST']


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


def test_new_owner_session_supersedes_an_unsaved_old_rotation(auth, monkeypatch):
    original = auth.path.__class__.replace
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(auth.path.__class__, 'replace', fail)
    with pytest.raises(BoostyUnavailable):
        auth.save({**auth.load(), 'access_token': 'unsaved-old-session'})
    monkeypatch.setattr(auth.path.__class__, 'replace', original)
    fresh = {**BoostyAuth().load(), 'access_token': 'fresh-owner-session'}
    BoostyAuth().save(fresh)
    assert auth.load() == fresh
    assert BoostyAuth().load() == fresh


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
