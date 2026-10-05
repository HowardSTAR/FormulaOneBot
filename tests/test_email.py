"""Mailer decision tables and failure paths. Every transport is a test double."""
import smtplib
from unittest.mock import MagicMock

import pytest

from app.emailer import (
    ConsoleMailer, EmailDeliveryError, MockMailer, SMTPConfig, SMTPMailer,
    YandexPostboxAPIMailer, build_mailer,
)


@pytest.fixture
def mail_environment(monkeypatch):
    for key in ('SMTP_HOST', 'SMTP_FROM_EMAIL', 'SMTP_USERNAME', 'SMTP_PASSWORD',
                'SMTP_PORT', 'SMTP_USE_SSL', 'SMTP_STARTTLS', 'SMTP_TIMEOUT_SECONDS',
                'YANDEX_POSTBOX_ACCESS_KEY_ID', 'YANDEX_POSTBOX_SECRET_ACCESS_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('SMTP_FROM_EMAIL', 'sender@example.test')


@pytest.mark.parametrize('mode,environment,expected', [
    pytest.param('mock', 'test', MockMailer, id='explicit-mock'),
    pytest.param('console', 'development', ConsoleMailer, id='development-console'),
    pytest.param('smtp', 'production', SMTPMailer, id='production-smtp'),
    pytest.param('postbox_api', 'production', YandexPostboxAPIMailer, id='postbox-alias'),
    pytest.param('yandex_postbox_api', 'production', YandexPostboxAPIMailer, id='postbox'),
])
def test_transport_selection(mail_environment, monkeypatch, mode, environment, expected):
    monkeypatch.setenv('EMAIL_DELIVERY_MODE', mode)
    monkeypatch.setenv('APP_ENV', environment)
    monkeypatch.setenv('YANDEX_POSTBOX_ACCESS_KEY_ID', 'test-key')
    monkeypatch.setenv('YANDEX_POSTBOX_SECRET_ACCESS_KEY', 'test-secret')
    assert isinstance(build_mailer(), expected)


@pytest.mark.parametrize('mode,environment', [
    pytest.param('console', 'production', id='console-in-production'),
    pytest.param('typo', 'test', id='unknown-mode'),
])
def test_unsafe_or_unknown_transport_rejected(mail_environment, monkeypatch, mode, environment):
    monkeypatch.setenv('EMAIL_DELIVERY_MODE', mode)
    monkeypatch.setenv('APP_ENV', environment)
    with pytest.raises(EmailDeliveryError):
        build_mailer()


@pytest.mark.parametrize('username,password,valid', [
    pytest.param(None, None, True, id='anonymous'),
    pytest.param('user', 'secret', True, id='authenticated'),
    pytest.param('user', None, False, id='missing-password'),
    pytest.param(None, 'secret', False, id='missing-username'),
])
def test_smtp_credentials_are_a_pair(mail_environment, monkeypatch, username, password, valid):
    if username is not None:
        monkeypatch.setenv('SMTP_USERNAME', username)
    if password is not None:
        monkeypatch.setenv('SMTP_PASSWORD', password)
    if valid:
        config = SMTPConfig.from_env()
        assert (config.username, config.password) == (username, password)
    else:
        with pytest.raises(EmailDeliveryError, match='together'):
            SMTPConfig.from_env()


@pytest.mark.parametrize('ssl,tls,expected', [
    pytest.param(False, True, ['ehlo', 'starttls', 'ehlo', 'login', 'send_message'], id='starttls'),
    pytest.param(True, True, ['login', 'send_message'], id='implicit-tls'),
    pytest.param(False, False, ['ehlo', 'login', 'send_message'], id='plain-explicit'),
])
async def test_verification_transport_order_and_message(monkeypatch, ssl, tls, expected):
    client = MagicMock()
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(smtplib, 'SMTP_SSL' if ssl else 'SMTP', factory)
    config = SMTPConfig('smtp.example.test', 465 if ssl else 587, 'user', 'secret', 'sender@example.test', use_ssl=ssl, start_tls=tls)
    await SMTPMailer(config).send_verification_code('recipient@example.test', '123456', 10)
    assert [call[0] for call in client.method_calls] == expected
    message = client.send_message.call_args.args[0]
    assert message['To'] == 'recipient@example.test'
    assert message['From'] == 'sender@example.test'
    assert '123456' in message.get_content() and '10 минут' in message.get_content()
    assert 'secret' not in message.as_string()


@pytest.mark.parametrize('error', [OSError('offline'), smtplib.SMTPException('rejected')], ids=['network', 'smtp'])
async def test_transport_failures_are_not_reported_as_success(monkeypatch, error):
    monkeypatch.setattr(smtplib, 'SMTP', MagicMock(side_effect=error))
    mailer = SMTPMailer(SMTPConfig('smtp.example.test', 587, None, None, 'sender@example.test'))
    with pytest.raises(EmailDeliveryError) as failure:
        await mailer.send_password_reset('recipient@example.test', 'https://example.test/reset?token=fake', 30)
    assert failure.value.__cause__ is error
