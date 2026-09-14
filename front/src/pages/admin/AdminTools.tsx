import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import "./admin-tools.css";
import { PredictionRecovery } from './PredictionRecovery';

const base = "/api/admin/tools";
const message = (e: unknown) => e instanceof Error ? e.message : "Ошибка запроса";
const deliveryLabels: Record<string,string> = { pending: "В очереди", sending: "Отправляется", sent: "Принято Telegram", retry: "Ожидает повтора", unknown: "Доставка не подтверждена", blocked: "Бот заблокирован", failed: "Ошибка", expired: "Срок истёк", cancelled: "Получатель исключён" };
type DeliveryBatch = { event_key: string; created: number; channel: string; counts: Record<string,number> };
function TelegramDeliveryLog() {
  const [rows, setRows] = useState<DeliveryBatch[]>([]);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try { setRows(await apiRequest<DeliveryBatch[]>(`${base}/telegram-deliveries`)); setError(""); }
    catch (e) { setError(message(e)); }
  }, []);
  useEffect(() => {
    let active = true;
    apiRequest<DeliveryBatch[]>(`${base}/telegram-deliveries`)
      .then(data => { if (active) setRows(data); })
      .catch(e => { if (active) setError(message(e)); });
    return () => { active = false; };
  }, []);
  return <section><h3>Доставка уведомлений · все каналы</h3>
    <button onClick={() => void refresh()}>Обновить статусы</button>
    <p>Последние 30 заданий общей очереди. Принятие сервисом не означает прочтение. Неопределённые отправки не повторяются автоматически во избежание дублей.</p>
    {error && <p role="alert">{error}</p>}
    {!error && !rows.length && <p>Рассылок в новой очереди пока нет.</p>}
    {rows.map(row => <article key={row.event_key}><h4>{row.channel === 'webpush' ? 'Web Push' : 'Telegram'} · {row.event_key}</h4><small>{new Date(row.created * 1000).toLocaleString()}</small>
      <p>{Object.entries(row.counts).map(([key,count]) => `${key === 'sent' ? 'Принято сервисом' : deliveryLabels[key] ?? key}: ${count}`).join(" · ") || "Нет получателей"}</p>
    </article>)}
  </section>;
}
type Insights = {
  accounts: { total: number; new_users: number; telegram_linked: number; verified_email: number };
  reach: { members: number; push_users: number };
  inbox: { total: number; read_count: number };
  queue: { pending: number; exhausted: number };
  visitors: { unique_browsers: number; returning_browsers: number };
  drivers: { label: string; users: number }[];
  registrations: { day: string; users: number }[];
  push_enabled: boolean;
};

export function AdminInsights() {
  const [days, setDays] = useState(30);
  const [state, setState] = useState<{ days: number; data?: Insights; error?: string } | null>(null);
  useEffect(() => {
    let active = true;
    apiRequest<Insights>(`${base}/insights`, { days }).then(data => { if (active) setState({ days, data }); })
      .catch(e => { if (active) setState({ days, error: message(e) }); });
    return () => { active = false; };
  }, [days]);
  const data = state?.days === days ? state.data : undefined;
  const error = state?.days === days ? state.error : undefined;
  const exportCsv = () => {
    if (!data) return;
    const rows = [["Показатель", "Значение"], ["Период, дней", days], ["Аккаунты сейчас", data.accounts.total],
      ["Новые аккаунты", data.accounts.new_users], ["Уникальные браузеры", data.visitors.unique_browsers],
      ["Вернувшиеся браузеры", data.visitors.returning_browsers], ["Получатели сайта сейчас", data.reach.members],
      ["Аккаунты с push сейчас", data.reach.push_users], ["Уведомления за период", data.inbox.total],
      ["Прочитано", data.inbox.read_count], ...data.registrations.map(r => [r.day, r.users])];
    const url = URL.createObjectURL(new Blob(["\uFEFF" + rows.map(row => row.map(v => `"${String(v ?? 0).replaceAll('"', '""')}"`).join(";")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = `analytics-${days}d.csv`; a.click(); URL.revokeObjectURL(url);
  };
  return <section className="admin-chart-card admin-tools"><header><h2>Аудитория и уведомления</h2>
    <div className="at-actions"><select aria-label="Период расширенной аналитики" value={days} onChange={e => setDays(Number(e.target.value))}>
      <option value={7}>7 дней</option><option value={30}>30 дней</option><option value={90}>90 дней</option>
    </select><button disabled={!data} onClick={exportCsv}>Скачать CSV</button></div></header>
    {error ? <p role="alert">{error}</p> : !data ? <p role="status">Загрузка…</p> : <>
      <div className="admin-metric-grid">{[["Аккаунтов сейчас", data.accounts.total], ["Новых за период", data.accounts.new_users],
        ["Браузеры за период", data.visitors.unique_browsers], ["Вернулись в другой день", data.visitors.returning_browsers],
        ["Получателей сайта сейчас", data.reach.members], ["Аккаунтов с push сейчас", data.reach.push_users]].map(([label, value]) =>
        <article key={label}><span>{label}</span><strong>{value ?? 0}</strong></article>)}</div>
      <p>Возвращаемость — визиты одного браузера в разные дни UTC внутри периода. Разные устройства и очистка cookie считаются отдельно. Архивные аккаунты исключены из статистики регистраций.</p>
      <div className="at-columns"><article><h3>Состояние каналов</h3>
        <p>Telegram привязан: {data.accounts.telegram_linked ?? 0}. Email подтверждён: {data.accounts.verified_email ?? 0}.</p>
        <p>Push на сервере: {data.push_enabled ? "настроен" : "не настроен"}. В очереди: {data.queue.pending ?? 0}. Исчерпаны попытки: {data.queue.exhausted ?? 0}.</p>
        <p>Уведомлений за период: {data.inbox.total}. Прочитано: {data.inbox.read_count ?? 0}.</p>
        <small>Очередь не подтверждает доставку на устройство. «Прочитать все» тоже считается прочтением.</small></article>
        <article><h3>Любимые пилоты аудитории</h3><small>Текущий срез, не зависит от периода</small>
          {data.drivers.length ? data.drivers.map(d => <p key={d.label}>{d.label} — {d.users} аккаунтов</p>) : <p>Пока нет данных</p>}</article></div>
      <details><summary>Регистрации по дням UTC</summary>{data.registrations.length ? data.registrations.map(r => <p key={r.day}>{r.day}: {r.users}</p>) : <p>Нет регистраций за период</p>}</details>
      <TelegramDeliveryLog />
    </>}
  </section>;
}

type Person = { id: number; display_name: string | null; telegram_username: string | null };
type Preview = { id: string; count: number; devices: number; sample: Person[]; push_enabled: boolean };
type Batch = { id: string; actor_id: number; title: string; body: string; url: string; created_at: number; sent_at: number | null; audience: number; recipients: number; queued: number; read_count: number };
const blank = { title: "", body: "", url: "/notifications", segment: "selected", user_ids: "", driver: "", push: false };

export function AdminNotifications({ adminId }: { adminId?: number }) {
  const [form, setForm] = useState(blank);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [history, setHistory] = useState<Batch[]>([]);
  const [search, setSearch] = useState("");
  const [people, setPeople] = useState<Person[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => setHistory((await apiRequest<{ items: Batch[] }>(`${base}/notifications`)).items), []);
  useEffect(() => { void load().catch(e => setError(message(e))); }, [load]);
  const edit = (patch: Partial<typeof blank>) => { setForm(v => ({ ...v, ...patch })); setPreview(null); setConfirmation(""); setNotice(""); };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await fn(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const prepare = () => void run(async () => {
    setPreview(null); setConfirmation(""); setNotice("");
    setPreview(await apiRequest<Preview>(`${base}/notifications/preview`, form, "POST")); await load();
  });
  const send = () => void run(async () => {
    if (!preview) return;
    const result = await apiRequest<{ recipients: number; queued: number; already_sent: boolean }>(`${base}/notifications/${preview.id}/send`, { confirmation }, "POST");
    setNotice(`${result.already_sent ? "Этот запрос уже выполнен. " : ""}В историю записано: ${result.recipients}. Push поставлено в очередь: ${result.queued}.`);
    setPreview(null); setConfirmation(""); await load();
  });
  return <section className="admin-chart-card admin-tools"><h2>Точечные уведомления</h2>
    <p>История на сайте + необязательный push. Не отправляет посты, email или сообщения в Telegram.</p>
    <p>Доступны только аккаунты, открывавшие раздел уведомлений сайта. Гости недоступны. Фильтры применяются вместе. Максимум 1000 получателей за отправку.</p>
    {error && <p role="alert" className="admin-notice error">{error}</p>}{notice && <p role="status">{notice}</p>}
    <fieldset disabled={busy}><div className="at-columns">
      <div className="at-fields"><label>Аудитория<select value={form.segment} onChange={e => edit({ segment: e.target.value })}>
        <option value="selected">Конкретные пользователи</option><option value="admins">Администраторы</option><option value="active">Активные за 30 дней</option><option value="inactive">Неактивные 30 дней</option><option value="all">Все получатели сайта</option>
      </select></label>
      {form.segment === "selected" && <><label>Поиск пользователя<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Имя, email или Telegram" /></label>
        <button onClick={() => void run(async () => setPeople((await apiRequest<{ items: Person[] }>("/api/admin/users", { search, page_size: 10 })).items))}>Найти</button>
        <div className="at-actions">{people.map(p => <button key={p.id} onClick={() => edit({ user_ids: [...new Set([...form.user_ids.split(/[,\s]+/).filter(Boolean), String(p.id)])].join(", ") })}>+ #{p.id} · {p.display_name || p.telegram_username || "Без имени"}</button>)}</div>
        <label>Внутренние ID, не Telegram ID<input value={form.user_ids} onChange={e => edit({ user_ids: e.target.value })} placeholder="12, 34" /></label>
        <button disabled={!adminId} onClick={() => edit({ user_ids: String(adminId), segment: "selected" })}>Выбрать только мой аккаунт</button></>}
      <label>Пилот в избранном — дополнительно<input value={form.driver} maxLength={3} placeholder="LEC; пусто — любой" onChange={e => edit({ driver: e.target.value.toUpperCase() })} /></label>
      <label className="at-check"><input type="checkbox" checked={form.push} onChange={e => edit({ push: e.target.checked })} />Также отправить push на подписанные устройства</label></div>
      <div className="at-fields"><label>Заголовок<input value={form.title} maxLength={120} onChange={e => edit({ title: e.target.value })} /></label>
        <label>Текст<textarea rows={7} value={form.body} maxLength={1500} onChange={e => edit({ body: e.target.value })} /></label><small>{form.body.length}/1500 · обычный текст, без HTML</small>
        <label>Переход внутри сайта<input value={form.url} onChange={e => edit({ url: e.target.value })} placeholder="/predictions" /></label>
        <article className="at-preview"><small>Предпросмотр</small><h3>{form.title || "Заголовок уведомления"}</h3><p>{form.body || "Текст уведомления"}</p><small>{form.url}</small></article></div>
    </div><button disabled={!form.title.trim() || !form.body.trim()} onClick={prepare}>Проверить аудиторию — без отправки</button>
    {preview && <article className="at-confirm"><h3>Получателей: {preview.count} · устройств с push: {preview.devices}</h3>
      <p>Список зафиксирован на час. Изменение формы сбросит подтверждение. Архивные аккаунты и ушедшие получатели исключаются при отправке.</p>
      {preview.sample.length > 0 && <p>Первые {preview.sample.length}: {preview.sample.map(p => `#${p.id} ${p.display_name || p.telegram_username || ""}`).join(", ")}</p>}
      {form.push && !preview.push_enabled && <p role="alert">Push не настроен. Отключите его и проверьте аудиторию заново.</p>}
      <label>Для реальной отправки введите ОТПРАВИТЬ<input value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="off" /></label>
      <button disabled={confirmation !== "ОТПРАВИТЬ" || !preview.count || (form.push && !preview.push_enabled)} onClick={send}>Отправить {preview.count} получателям</button>
    </article>}</fieldset>
    <header><h3>Последние 50 проверок и отправок</h3><button disabled={busy} onClick={() => void run(load)}>Обновить</button></header>
    <p>Повтор запроса не создаёт дубликаты. Новая проверка — независимая отправка. Очередь push не означает доставку.</p>
    {!history.length && <p>Пока нет отправок</p>}
    <div className="at-history">{history.map(b => <article key={b.id}><h4>{b.title}</h4><small>{new Date(b.created_at * 1000).toLocaleString("ru-RU")} · автор #{b.actor_id}</small>
      <p>{b.sent_at ? `В историю: ${b.recipients} · прочитано: ${b.read_count} · push в очередь: ${b.queued}` : `Проверка аудитории: ${b.audience}. Не отправлено.`}</p>
      <details><summary>Текст и ссылка</summary><p>{b.body}</p><code>{b.url}</code></details></article>)}</div>
  </section>;
}

export function AdminToolDirectory() {
  return <section className="admin-chart-card admin-tools"><h2>Административные инструменты</h2><p>Что уже есть и где находится</p><div className="at-columns">
    <article><h3>В этой админке</h3><p>Аналитика: активность сайта/бота, гости, популярные страницы, регистрации, возвращаемость и CSV.</p><p>Пользователи: поиск, роли, email, отвязка Telegram и восстановление доступа. Изменение ролей защищено правами superadmin.</p><p>Игры: статистика и управление рекордами. Журнал: история административных действий.</p></article>
    <article><h3><Link to="/prediction-analytics">Аналитика предсказаний →</Link></h3><p>Отдельная закрытая страница: расчёты вероятностей, история прогнозов и их результаты.</p><h3><Link to="/notifications">Мои уведомления →</Link></h3><p>Алёрты об ошибках для администратора и настройка push на текущем устройстве.</p></article>
    <article><h3>Диагностика в Telegram-боте</h3><p><code>/check_broadcast</code> — диагностика рассылок; <code>/check_results</code> — проверка результатов.</p><p>В боте также есть принудительные рассылки и /broadcast. Здесь они не запускаются: могут отправлять реальные сообщения.</p></article>
    <article><h3>Новые точечные уведомления</h3><p>Вкладка «Уведомления»: аудитория, предпросмотр, подтверждение, история и число прочитанных сообщений.</p><p>Публикация постов исключена. Новая форма не отправляет email и Telegram-сообщения.</p></article>
  </div><PredictionRecovery /></section>;
}
