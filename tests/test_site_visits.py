import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_guest_visits_deduplicate_and_metrics_include_new_guests(api_client, app_with_overrides):
    from app.api.admin_api import AdminContext, require_admin_session
    from app.db import get_or_create_user
    admin_id = await get_or_create_user(999888)
    app_with_overrides.dependency_overrides[require_admin_session] = lambda: AdminContext(id=admin_id, role="superadmin")
    for _ in range(3):
        result = await api_client.post('/api/analytics/visit', json={'path': '/race-game'})
        assert result.status_code == 200, result.text
    await api_client.post('/api/analytics/visit', json={'path': '/wiki'})
    async with AsyncClient(transport=ASGITransport(app=app_with_overrides), base_url='http://guest') as guest:
        assert (await guest.post('/api/analytics/visit', json={'path': '/race-game'})).status_code == 200
    metrics = (await api_client.get('/api/admin/metrics')).json()['visits']
    assert metrics['visitors'] == 2
    assert metrics['guests'] == 2
    assert metrics['signed_in'] == 0
    assert metrics['page_visits'] == 3
    assert metrics['top_pages'][0] == {'path': '/race-game', 'visitors': 2}


@pytest.mark.asyncio
async def test_visit_does_not_accept_search_parameters_or_cross_site_posts(api_client):
    assert (await api_client.post('/api/analytics/visit', json={'path': '/?email=private'})).status_code == 422
    assert (await api_client.post('/api/analytics/visit', json={'path': '/'}, headers={'sec-fetch-site': 'cross-site'})).status_code == 403


@pytest.mark.asyncio
async def test_login_links_guest_visits_without_adding_a_new_visitor(api_client, app_with_overrides, monkeypatch):
    from app.api import site_analytics
    from app.db import db
    await api_client.post('/api/analytics/visit', json={'path': '/'})
    async def authenticated(**kwargs):
        return 42
    monkeypatch.setattr(site_analytics, 'require_hybrid_user_id', authenticated)
    await api_client.post('/api/analytics/visit', json={'path': '/wiki'})
    async with db.conn.execute('SELECT COUNT(DISTINCT visitor_id), COUNT(DISTINCT user_id), SUM(user_id IS NULL) FROM site_visits') as cursor:
        row = await cursor.fetchone()
    assert tuple(row) == (1, 1, 0)
