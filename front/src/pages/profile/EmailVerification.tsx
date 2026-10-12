import { useState, type FormEvent } from 'react';
import { apiRequest } from '../../helpers/api';
import { notifyAuthChanged } from '../../helpers/auth';
import './email-verification.css';

export default function EmailVerification({ email, emailSent = true, registered = false }: {
  email: string; emailSent?: boolean; registered?: boolean;
}) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState(emailSent ? '' : 'Письмо пока не удалось отправить. Запросите код повторно.');
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
    setBusy(true); setError(''); setMessage('');
    try {
      await apiRequest('/api/auth/resend-verification', {}, 'POST');
      setCode(''); setMessage('Новый код отправлен. Он действует 10 минут.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось отправить код'); }
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
      <button type="button" className="profile-email-resend" disabled={busy} onClick={() => void resend()}>Отправить код повторно</button>
    </form>
    {error && <p role="alert" className="profile-email-error">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
