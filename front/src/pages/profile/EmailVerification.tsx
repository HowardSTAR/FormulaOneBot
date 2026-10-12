import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { apiRequest } from '../../helpers/api';
import { notifyAuthChanged } from '../../helpers/auth';
import './email-verification.css';

type VerificationStatus = { retry_after: number };

export default function EmailVerification({ email, emailSent = true, registered = false }: {
  email: string; emailSent?: boolean; registered?: boolean;
}) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState(emailSent ? '' : 'Письмо пока не удалось отправить. Запросите код повторно.');
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(Date.now);
  const remaining = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const coolingDown = remaining > 0;
  const setCooldown = useCallback((seconds: number) => {
    const timestamp = Date.now();
    setNow(timestamp); setResendAt(timestamp + Math.max(0, seconds) * 1000);
  }, []);
  useEffect(() => {
    let active = true;
    void apiRequest<VerificationStatus>('/api/auth/verification-status').then(status => {
      if (active) setCooldown(status.retry_after);
    }).catch(() => { /* The server still enforces the interval if status cannot be loaded. */ })
      .finally(() => { if (active) setStatusLoaded(true); });
    return () => { active = false; };
  }, [email, setCooldown]);
  useEffect(() => {
    if (!coolingDown) return;
    const tick = () => setNow(Date.now());
    const timer = window.setInterval(tick, 1000);
    document.addEventListener('visibilitychange', tick);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', tick); };
  }, [resendAt, coolingDown]);
  const verify = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try {
      const result = await apiRequest<{ csrf_token: string }>('/api/auth/verify-email', { email, code }, 'POST');
      sessionStorage.setItem('turbotears_csrf', result.csrf_token);
      notifyAuthChanged();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось подтвердить email'); }
    finally { setBusy(false); }
  };
  const resend = async () => {
    if (busy || coolingDown || !statusLoaded) return;
    setBusy(true); setError(''); setMessage('');
    setCooldown(60);
    try {
      const status = await apiRequest<VerificationStatus>('/api/auth/resend-verification', {}, 'POST');
      setCooldown(status.retry_after);
      setCode(''); setMessage('Новый код отправлен. Он действует 10 минут.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось отправить код');
      try {
        const status = await apiRequest<VerificationStatus>('/api/auth/verification-status');
        setCooldown(status.retry_after);
      } catch { /* Keep the local interval when the connection is unavailable. */ }
    }
    finally { setBusy(false); }
  };
  return <section className="profile-panel profile-email-verification" aria-labelledby="profile-email-title">
    <span className="profile-eyebrow">{registered ? 'ДОБРО ПОЖАЛОВАТЬ В TURBOTEARS' : 'ЗАВЕРШИТЬ РЕГИСТРАЦИЮ'}</span>
    <h2 id="profile-email-title">{registered ? 'Профиль готов — подтвердите email' : 'Подтвердите email'}</h2>
    <p>Введите шестизначный код из письма на <strong>{email}</strong>. Код действует 10 минут. Можно сделать это сейчас или вернуться позже.</p>
    <form onSubmit={verify}>
      <label>Код из письма<input autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6}
        required disabled={busy} value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} placeholder="000000" /></label>
      <button type="submit" disabled={busy || code.length !== 6}>{busy ? 'Подождите…' : 'Подтвердить email'}</button>
      <button type="button" className="profile-email-resend" disabled={busy || coolingDown || !statusLoaded} aria-describedby="profile-email-resend-hint" onClick={() => void resend()}>
        Прислать письмо заново{coolingDown && ` · ${Math.floor(remaining / 60).toString().padStart(2, '0')}:${(remaining % 60).toString().padStart(2, '0')}`}
      </button>
    </form>
    <p id="profile-email-resend-hint" className="profile-email-resend-hint">Повторное письмо можно запросить раз в минуту.</p>
    {error && <p role="alert" className="profile-email-error">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
