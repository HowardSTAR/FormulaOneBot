"""User-facing error text is Russian; machine codes and input redaction remain stable."""

import re

import httpx
import pytest

from app.api import auth_api
from app.api.miniapp_api import web_app
from app.api.validation_messages import validation_message
from app.emailer import MockMailer
from app.services.auth_service import AuthService
from app.services.account_link_service import AccountLinkService, LinkNotFound


@pytest.mark.parametrize("error,expected", [
    ({"type": "missing", "loc": ["body", "email"]}, 'Заполните поле «Email».'),
    ({"type": "string_too_short", "loc": ["body", "password"], "ctx": {"min_length": 15}}, 'Поле «Пароль» должно содержать не менее 15 символов.'),
    ({"type": "string_pattern_mismatch", "loc": ["body", "code"]}, 'Введите код из шести цифр.'),
    ({"type": "value_error", "msg": "Value error, Сезон ещё не начался"}, 'Сезон ещё не начался'),
    ({"type": "value_error", "msg": "Value error, SECRET backend details", "input": "SECRET"}, 'Проверьте введённые данные.'),
    ({"type": "unknown", "msg": "Unknown exception SECRET"}, 'Проверьте введённые данные.'),
])
def test_validation_messages_are_safe_russian(error, expected):
    assert validation_message(error) == expected


async def test_auth_http_messages_are_russian_and_do_not_echo_passwords(db_session, monkeypatch):
    auth = AuthService(db_session, MockMailer(), pepper="russian-error-tests")
    monkeypatch.setattr(auth_api, "get_auth_service", lambda: auth)
    transport = httpx.ASGITransport(app=web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        cases = [
            ("GET", "/api/auth/me", None, 401),
            ("POST", "/api/auth/register", {"email": "fan@example.test", "password": "SECRET-short", "display_name": "Pilot"}, 422),
            ("POST", "/api/auth/register", {"email": "invalid-email", "password": "A unique long racing passphrase", "display_name": "Pilot"}, 422),
            ("POST", "/api/auth/verify-email", {"email": "fan@example.test", "code": "bad"}, 422),
            ("POST", "/api/auth/login", {"email": "fan@example.test", "password": "SECRET-password"}, 401),
            ("POST", "/api/auth/login", {}, 422),
        ]
        for method, path, payload, status in cases:
            response = await client.request(method, path, json=payload)
            assert response.status_code == status
            detail = response.json()["detail"]
            messages = [item["msg"] for item in detail] if isinstance(detail, list) else [detail["message"]]
            assert all(re.search(r"[А-Яа-яЁё]", message) for message in messages)
            assert "SECRET" not in response.text
            assert '"input"' not in response.text
        assert (await client.get("/api/auth/me")).json()["detail"]["code"] == "missing_session"


async def test_bot_link_errors_are_also_russian(db_session):
    links = AccountLinkService(db_session, pepper="russian-error-tests")
    with pytest.raises(LinkNotFound, match="Неверный код"):
        await links.approve_web_short_code("123456", 12345)
