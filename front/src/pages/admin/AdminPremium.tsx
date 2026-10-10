import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';

type Mode = 'enabled' | 'disabled' | 'boosty';
type PremiumStatus = { active: boolean; premium_active: boolean; premium_override: boolean | null };

export function AdminPremium() {
  const [status, setStatus] = useState<PremiumStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    void apiRequest<PremiumStatus>('/api/admin/me/premium').then(value => {
      if (active) setStatus(value);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : 'Не удалось загрузить премиум');
    });
    return () => { active = false; };
  }, []);

  const change = async (mode: Mode) => {
    setBusy(true); setError(''); setMessage('');
    try {
      const value = await apiRequest<PremiumStatus>('/api/admin/me/premium', { mode }, 'PATCH');
      setStatus(value);
      setMessage(mode === 'boosty' ? 'Премиум снова зависит от подписки Boosty.' : `Премиум ${value.premium_active ? 'включён' : 'отключён'} вручную.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось изменить премиум');
    } finally { setBusy(false); }
  };
  const mode = !status || status.premium_override === null ? 'boosty' : status.premium_override ? 'enabled' : 'disabled';

  return <section className="admin-users-card admin-premium" aria-labelledby="own-premium-title" aria-busy={busy}>
    <h3 id="own-premium-title">Мой премиум</h3>
    <p>Ручной выбор действует только для вашего аккаунта и сохраняется независимо от проверок Boosty.</p>
    <p role="status">{!status ? 'Загружаем статус…' : `Премиум ${status.premium_active ? 'включён' : 'отключён'} · ${mode === 'boosty' ? 'по подписке Boosty' : 'вручную'}`}</p>
    <div className="admin-premium-actions">
      <button type="button" disabled={busy || !status || mode === 'enabled'} onClick={() => void change('enabled')}>Включить премиум</button>
      <button type="button" disabled={busy || !status || mode === 'disabled'} onClick={() => void change('disabled')}>Отключить премиум</button>
      <button type="button" disabled={busy || !status || mode === 'boosty'} onClick={() => void change('boosty')}>По подписке Boosty</button>
    </div>
    {busy && <p role="status">Сохраняем…</p>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
