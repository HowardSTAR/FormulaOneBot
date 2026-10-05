"""Equivalence partitions and UTF-8 byte boundaries for the public auth contract."""
import pytest
from app.services.auth_service import InvalidInput, normalize_email, validate_password
from tests.support import Clock


@pytest.mark.parametrize('value,expected', [
    pytest.param('  Driver@EXAMPLE.TEST  ', 'driver@example.test', id='trim-and-normalize'),
    pytest.param('a'*64+'@example.test', 'a'*64+'@example.test', id='local-part-max'),
    pytest.param('a'+'@'+'b'*248+'.com', 'a'+'@'+'b'*248+'.com', id='total-max-254'),
])
def test_valid_email_partitions(value, expected):
    assert normalize_email(value) == expected
    assert normalize_email(normalize_email(value)) == expected


@pytest.mark.parametrize('value', [
    pytest.param('', id='empty'), pytest.param('a@example', id='no-domain-suffix'),
    pytest.param('a b@example.test', id='internal-whitespace'),
    pytest.param('a@@example.test', id='two-at-signs'),
    pytest.param('a'*65+'@example.test', id='local-part-65'),
    pytest.param('a@'+'b'*249+'.com', id='total-255'),
])
def test_invalid_email_partitions(value):
    with pytest.raises(InvalidInput):
        normalize_email(value)


@pytest.mark.parametrize('password,valid', [
    pytest.param('a1'+'x'*9, False, id='11-characters'),
    pytest.param('a1'+'x'*10, True, id='12-characters'),
    pytest.param('a1'+'x'*70, True, id='72-ascii-bytes'),
    pytest.param('a1'+'x'*71, False, id='73-ascii-bytes'),
    pytest.param('a1'+'я'*35, True, id='72-utf8-bytes'),
    pytest.param('a1x'+'я'*35, False, id='73-utf8-bytes'),
    pytest.param('abcdefghijklm', False, id='missing-number'),
    pytest.param('1234567890123', False, id='missing-letter'),
])
def test_password_boundary_decisions(password, valid):
    if valid:
        assert validate_password(password) is None
    else:
        with pytest.raises(InvalidInput):
            validate_password(password)


@pytest.mark.parametrize('seconds,valid',[pytest.param(599.999,True,id='before-expiry'),
    pytest.param(600,False,id='at-expiry'),pytest.param(600.001,False,id='after-expiry')])
async def test_verification_expiry_and_single_use(db_session,monkeypatch,seconds,valid):
    from app.services import auth_service
    from app.emailer import MockMailer
    clock,mailer = Clock(),MockMailer()
    monkeypatch.setattr(auth_service,'utc_now',lambda:clock.now)
    auth = auth_service.AuthService(db_session,mailer,pepper='boundary-tests')
    await auth.register('boundary@example.test','FormulaOne-2026-Secure')
    code = mailer.messages[-1]['code']
    clock.advance(seconds=seconds)
    if valid:
        session = await auth.verify_email('boundary@example.test',code)
        assert session.user['email_verified'] is True
        with pytest.raises(auth_service.InvalidVerificationCode):
            await auth.verify_email('boundary@example.test',code)
    else:
        with pytest.raises(auth_service.VerificationCodeExpired):
            await auth.verify_email('boundary@example.test',code)
        assert (await (await db_session.conn.execute('SELECT email_verified FROM users')).fetchone())[0] == 0


@pytest.mark.parametrize('transition',['logout','archived','expired','tampered','foreign-token'])
async def test_session_invalidating_transitions(db_session,monkeypatch,transition):
    from app.services import auth_service
    from app.emailer import MockMailer
    clock,mailer = Clock(),MockMailer()
    monkeypatch.setattr(auth_service,'utc_now',lambda:clock.now)
    auth = auth_service.AuthService(db_session,mailer,pepper='state-tests')
    await auth.register('session@example.test','FormulaOne-2026-Secure')
    session = await auth.verify_email('session@example.test',mailer.messages[-1]['code'])
    assert (await auth.authenticate_session(session.token))['id'] == session.user['id']
    token = session.token
    if transition=='logout':
        await auth.logout(token)
    elif transition=='archived':
        await db_session.conn.execute('UPDATE users SET archived_at=?',(clock.now.isoformat(),))
        await db_session.conn.commit()
    elif transition=='expired':
        clock.advance(seconds=30*86400)
    elif transition=='tampered':
        token = ('a' if token[0]!='a' else 'b')+token[1:]
    else:
        token = 'other-identity-token'
    with pytest.raises(auth_service.InvalidCredentials):
        await auth.authenticate_session(token)
