import { SelectField } from '../../components/CustomSelect';
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import "./admin-tools.css";

const base = "/api/admin/tools";
const message = (e: unknown) => e instanceof Error ? e.message : "Ошибка запроса";
type Person = { id: number; display_name: string | null; telegram_username: string | null };
type Preview = { id: string; count: number; devices: number; sample: Person[]; push_enabled: boolean };
type Batch = { id: string; actor_id: number; title: string; body: string; url: string; created_at: number; sent_at: number | null; audience: number; recipients: number; queued: number; read_count: number };
const segments = {
  selected: 'Конкретные пользователи', admins: 'Администраторы', active: 'Активные за 30 дней',
  inactive: 'Неактивные 30 дней', all: 'Все получатели сайта',
};
const blank = { title: "", body: "", url: "/notifications", segment: "selected", user_ids: "", driver: "", push: false };

export function AdminNotifications({ adminId }: { adminId?: number }) {
  const [view, setView] = useState<"compose" | "history">("compose");
  const [form, setForm] = useState(blank);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [history, setHistory] = useState<Batch[] | null>(null);
  const [search, setSearch] = useState("");
  const [people, setPeople] = useState<Person[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => setHistory((await apiRequest<{ items: Batch[] }>(`${base}/notifications`)).items), []);
  useEffect(() => { if (view === "history") void load().catch(e => setError(message(e))); }, [view, load]);
  const edit = (patch: Partial<typeof blank>) => { setForm(v => ({ ...v, ...patch })); setPreview(null); setConfirmation(""); setNotice(""); };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await fn(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const prepare = () => void run(async () => {
    setPreview(null); setConfirmation(""); setNotice("");
    setPreview(await apiRequest<Preview>(`${base}/notifications/preview`, form, "POST"));
  });
  const send = () => void run(async () => {
    if (!preview) return;
    const result = await apiRequest<{ recipients: number; queued: number; already_sent: boolean }>(`${base}/notifications/${preview.id}/send`, { confirmation }, "POST");
    setNotice(`${result.already_sent ? "Этот запрос уже выполнен. " : ""}В историю записано: ${result.recipients}. Push поставлено в очередь: ${result.queued}.`);
    setPreview(null); setConfirmation(""); setForm(blank); setView("history");
  });
  return <section className="admin-chart-card admin-tools"><nav className="admin-inline-actions admin-subnav" aria-label="Рассылки сайта">
      <button type="button" disabled={busy} aria-pressed={view === "compose"} onClick={() => { setError(""); setView("compose"); }}>Новая рассылка</button>
      <button type="button" disabled={busy} aria-pressed={view === "history"} onClick={() => { setError(""); setView("history"); }}>История</button>
    </nav>
    {error && <p role="alert" className="admin-notice error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {view === "compose" && <fieldset disabled={busy}>
      {!preview && <><p>До 1000 получателей из числа пользователей, открывавших уведомления сайта. Push можно подключить к рассылке.</p>
      <div className="at-columns">
      <div className="at-fields"><label>Аудитория<SelectField value={form.segment} onChange={e => edit({ segment: e })}>
        {Object.entries(segments).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </SelectField></label>
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
      </div>
    </div><button className="admin-primary-action" disabled={!form.title.trim() || !form.body.trim()} onClick={prepare}>Проверить аудиторию</button></>}
    {preview && <article className="at-confirm"><h3>Проверьте перед отправкой</h3>
      <p><strong>{segments[form.segment as keyof typeof segments]}</strong>{form.driver && ` · пилот ${form.driver}`}</p>
      <dl className="admin-review-metrics">
        <div><dt>Получатели</dt><dd>{preview.count}</dd></div>
        <div><dt>Push</dt><dd>{form.push ? `${preview.devices} устройств` : "Выключен"}</dd></div>
      </dl>
      <div className="admin-message-preview"><h4>{form.title}</h4><p>{form.body}</p><small>Переход: {form.url}</small></div>
      <p>Список зафиксирован на час. Изменение формы сбросит подтверждение. Архивные аккаунты и ушедшие получатели исключаются при отправке.</p>
      {preview.sample.length > 0 && <p>Первые {preview.sample.length}: {preview.sample.map(p => `#${p.id} ${p.display_name || p.telegram_username || ""}`).join(", ")}</p>}
      {form.push && !preview.push_enabled && <p role="alert">Push не настроен. Отключите его и проверьте аудиторию заново.</p>}
      <label>Для реальной отправки введите ОТПРАВИТЬ<input value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="off" /></label>
      <div className="admin-inline-actions">
        <button type="button" onClick={() => { setPreview(null); setConfirmation(""); setError(""); }}>Вернуться к редактированию</button>
        <button type="button" className="admin-primary-action" disabled={confirmation !== "ОТПРАВИТЬ" || !preview.count || (form.push && !preview.push_enabled)} onClick={send}>Отправить {preview.count} получателям</button>
      </div>
    </article>}</fieldset>}
    {view === "history" && <><header><h3>Последние 50 проверок и отправок</h3><button disabled={busy} onClick={() => void run(load)}>Обновить</button></header>
    <p>Повтор запроса не создаёт дубликаты. Новая проверка — независимая отправка. Очередь push не означает доставку.</p>
    {history === null && !error && <p role="status">Загружаем историю…</p>}
    {history?.length === 0 && <p>Пока нет отправок</p>}
    <div className="at-history">{history?.map(b => <article key={b.id}><h4>{b.title}</h4><small>{new Date(b.created_at * 1000).toLocaleString("ru-RU")} · автор #{b.actor_id}</small>
      <p>{b.sent_at ? `Записано в уведомления: ${b.recipients} · push поставлено в очередь: ${b.queued} · отмечено прочитанным: ${b.read_count}` : `Проверка аудитории: ${b.audience}. Не отправлено.`}</p>
      <details><summary>Текст и ссылка</summary><p>{b.body}</p><code>{b.url}</code></details></article>)}</div></>}
  </section>;
}

export function AdminToolDirectory() {
  return <section className="admin-chart-card admin-tools" aria-label="Быстрые переходы">
    <ul className="admin-tool-links">
      <li><Link to="/admin?section=control">Сообщение не дошло</Link><p>Выберите канал и проверьте статус задания. В боте используйте <code>/check_broadcast</code>.</p></li>
      <li><Link to="/admin?section=recovery">В результатах не хватает факта</Link><p>Откройте нужный этап и запустите проверку. В боте доступна команда <code>/check_results</code>.</p></li>
      <li><Link to="/prediction-analytics">Проверить математический прогноз</Link><p>Версии модели, вероятности и сравнение с результатами.</p></li>
      <li><Link to="/notifications">Получать уведомления об ошибках</Link><p>Откройте уведомления и настройте push на текущем устройстве.</p></li>
    </ul>
  </section>;
}
