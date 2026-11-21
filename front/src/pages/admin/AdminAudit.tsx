import { useEffect, useState } from 'react';
import { SelectField } from '../../components/CustomSelect';
import { apiRequest } from '../../helpers/api';
import { auditActionLabels, describeAuditChange } from '../../helpers/adminAudit';

type AuditItem = {
  id: number; action: string; created_at: string; target_user_id: number | null;
  actor_user_id: number | null; actor_email: string | null; actor_telegram_id: number | null;
  details: Record<string, unknown>;
};
type Filters = { date_from: string; date_to: string; actor: string; target_user_id: string; action: string };
type AuditPage = { items: AuditItem[]; next_before: number | null };
const blank: Filters = { date_from: '', date_to: '', actor: '', target_user_id: '', action: '' };
const date = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short', timeZone: 'UTC' });

export function AdminAudit({ userId, revision = 0 }: { userId?: number; revision?: number }) {
  const [draft, setDraft] = useState(blank);
  const [filters, setFilters] = useState(blank);
  const [cursors, setCursors] = useState<number[]>([]);
  const [attempt, setAttempt] = useState(0);
  const before = cursors.at(-1);
  const key = JSON.stringify([filters, before, userId, attempt, revision]);
  const [result, setResult] = useState<{ key: string; data?: AuditPage; error?: string }>();
  useEffect(() => {
    let active = true;
    const query = Object.fromEntries(Object.entries(filters).filter(([, value]) => value.trim()));
    void apiRequest<AuditPage>('/api/admin/audit-log', { ...query, before, limit: userId ? 10 : 25, target_user_id: userId ?? (filters.target_user_id || undefined) })
      .then(data => { if (active) setResult({ key, data }); })
      .catch(error => { if (active) setResult({ key, error: error instanceof Error ? error.message : 'Не удалось загрузить журнал' }); });
    return () => { active = false; };
  }, [before, filters, key, userId]);
  const current = result?.key === key ? result : undefined;
  const edit = (name: keyof Filters, value: string) => setDraft(previous => ({ ...previous, [name]: value }));

  return <section className={userId ? 'admin-user-history' : 'admin-audit-card'}>
    {!userId && <form className="admin-audit-filters" onSubmit={event => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      setFilters({ ...draft, date_from: String(fields.get('date_from') ?? ''), date_to: String(fields.get('date_to') ?? '') });
      setCursors([]);
    }}>
      <label>С даты (UTC)<input type="date" name="date_from" /></label>
      <label>По дату (UTC)<input type="date" name="date_to" /></label>
      <label>Автор<input value={draft.actor} maxLength={254} placeholder="Email или ID…" onChange={event => edit('actor', event.target.value)} /></label>
      <label>ID пользователя<input type="number" min="1" value={draft.target_user_id} onChange={event => edit('target_user_id', event.target.value)} /></label>
      <label>Действие<SelectField value={draft.action} onChange={value => edit('action', value)}>
        <option value="">Все действия</option>{Object.entries(auditActionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </SelectField></label>
      <div className="admin-inline-actions">
        <button type="submit">Найти события</button>
        <button type="reset" onClick={() => { setDraft(blank); setFilters(blank); setCursors([]); }}>Сбросить</button>
      </div>
    </form>}
    {!current && <p role="status">Загружаем журнал…</p>}
    {current?.error && <div role="alert"><p>{current.error}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Повторить загрузку</button></div>}
    {current?.data && <>
      {!current.data.items.length && <p role="status">Событий по выбранным условиям нет.</p>}
      <ol className="admin-event-list">
        {current.data.items.map(item => <li key={item.id}>
          <div className="admin-event-heading">
            <strong>{auditActionLabels[item.action] || item.action}</strong>
            <time dateTime={item.created_at}>{date.format(new Date(item.created_at))} UTC</time>
          </div>
          <p>Автор: {item.actor_email || (item.actor_telegram_id ? `Telegram #${item.actor_telegram_id}` : item.actor_user_id ? `#${item.actor_user_id}` : 'Удалённый аккаунт')}{!userId && item.target_user_id ? ` · Пользователь #${item.target_user_id}` : ''}</p>
          <p>{describeAuditChange(item.action, item.details)}</p>
          {!userId && <details><summary>Технические сведения</summary><code>{JSON.stringify(item.details)}</code></details>}
        </li>)}
      </ol>
      {(cursors.length > 0 || current.data.next_before) && <nav className="admin-inline-actions" aria-label="Страницы журнала">
        <button type="button" disabled={!cursors.length} onClick={() => setCursors(previous => previous.slice(0, -1))}>Новее</button>
        <button type="button" disabled={!current.data.next_before} onClick={() => {
          const next = current.data?.next_before;
          if (next) setCursors(previous => [...previous, next]);
        }}>Старше</button>
      </nav>}
    </>}
  </section>;
}
