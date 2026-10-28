import { CustomSelect } from '../../components/CustomSelect';
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { BackButton } from "../../components/BackButton";
import { HomeIcon } from "../index/HomeIcon";
import "./notifications.css";
import { notificationBody, NOTIFICATIONS_CHANGED_EVENT } from '../../helpers/notificationPresentation';
import { reminderBody, reminderClock, type ReminderTiming } from '../../helpers/reminderClock';
import { visibleInterval } from '../../helpers/visibleInterval';

type Item = { id: number; title: string; body: string; url: string; created_at: number; read_at: number | null; reminder?: ReminderTiming | null; historical_snapshot?: boolean; priority?: "minimal" | "low" | "medium" | "critical" | "blocking" | null };
const priorityNames = { minimal: "Минимальный", low: "Низкий", medium: "Средний", critical: "Критический", blocking: "Блокирующий" };
type Inbox = { items: Item[]; unread: number; next_before: number | null; push: { enabled: boolean; public_key: string } };
function groupNotifications(items: Item[]) {
  const groups = new Map<string, Item & { copies: number }>();
  for (const item of items) {
    const key = JSON.stringify([item.url, item.title, item.reminder ? ['reminder', item.reminder.start_utc] : ['body', item.body]]);
    const previous = groups.get(key);
    if (previous) {
      previous.copies += 1;
      if (!item.read_at) previous.read_at = null;
    } else groups.set(key, { ...item, copies: 1 });
  }
  return [...groups.values()];
}
function keyBytes(key: string) {
  const value = atob(key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4-key.length%4)%4));
  return Uint8Array.from(value, char => char.charCodeAt(0));
}
const supported = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export default function NotificationsPage() {
  const [data, setData] = useState<Inbox | null>(null);
  const [error, setError] = useState("");
  const [pushBusy, setPushBusy] = useState(false);
  const [moreBusy, setMoreBusy] = useState(false);
  const [readBusy, setReadBusy] = useState(false);
  const [pushError, setPushError] = useState("");
  const [readError, setReadError] = useState("");
  const [moreError, setMoreError] = useState("");
  const [category, setCategory] = useState('all');
  const [now, setNow] = useState(() => Date.now());
  const hasReminders = !!data?.items.some(item => item.reminder);
  useEffect(() => {
    if (!hasReminders) return;
    return visibleInterval(() => setNow(Date.now()), 1000);
  }, [hasReminders]);
  const requestSequence = useRef(0);
  const [subscribed, setSubscribed] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    supported() ? Notification.permission : "unsupported",
  );
  const standalone = window.matchMedia("(display-mode: standalone)").matches
    || !!(navigator as Navigator & { standalone?: boolean }).standalone;
  const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent)
    || (/Macintosh/i.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  const refresh = useCallback(async () => {
    const sequence = ++requestSequence.current;
    try { const result = await apiRequest<Inbox>("/api/web-notifications", {category}); if (sequence === requestSequence.current) {setData(result); setError('');} }
    catch (e) { if (sequence === requestSequence.current) setError(e instanceof Error ? e.message : "Не удалось загрузить уведомления"); }
  }, [category]);
  useEffect(() => {
    void refresh();
    let alive = true;
    const syncPermission = () => { if (supported()) setPermission(Notification.permission); };
    if (supported()) void navigator.serviceWorker.getRegistration("/").then(async reg => {
      const sub = await reg?.pushManager.getSubscription();
      if (alive) setSubscribed(!!sub);
    }).catch(() => {});
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 60000);
    window.addEventListener("focus", syncPermission);
    document.addEventListener("visibilitychange", syncPermission);
    return () => {
      alive = false;
      clearInterval(timer);
      window.removeEventListener("focus", syncPermission);
      document.removeEventListener("visibilitychange", syncPermission);
    };
  }, [refresh]);
  const togglePush = async () => {
    if (!supported() || pushBusy) return;
    setPushBusy(true); setPushError("");
    try {
      if (subscribed) {
        const reg = await navigator.serviceWorker.getRegistration("/");
        const sub = await reg?.pushManager.getSubscription();
        if (sub) {
          await apiRequest("/api/web-notifications/subscription", { endpoint: sub.endpoint }, "DELETE");
          await sub.unsubscribe();
        }
        setSubscribed(false); return;
      }
      // Permission is requested only from this explicit user gesture.
      if (Notification.permission === "denied") {
        setPermission("denied");
        throw new Error("Уведомления заблокированы в браузере. Разрешите их для f1hub.ru по инструкции ниже.");
      }
      const nextPermission = await Notification.requestPermission();
      setPermission(nextPermission);
      if (nextPermission !== "granted") throw new Error("Браузер не разрешил уведомления. Проверьте разрешения сайта по инструкции ниже.");
      try { await navigator.serviceWorker.register("/notifications-sw.js", { scope: "/" }); }
      catch { throw new Error("Не удалось запустить push-службу. Обновите страницу; если ошибка останется, переустановите приложение TurboTears."); }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription() || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(data!.push.public_key) });
      const keys = sub.toJSON().keys!;
      try { await apiRequest("/api/web-notifications/subscription", { endpoint:sub.endpoint,p256dh:keys.p256dh,auth:keys.auth }, "POST"); }
      catch (e) { await sub.unsubscribe(); throw e; }
      setSubscribed(true);
    } catch (e) { setPushError(e instanceof Error ? e.message : "Не удалось изменить подписку"); }
    finally { setPushBusy(false); }
  };
  const markRead = async () => {
    if (!data?.items.length || readBusy) return;
    setReadBusy(true); setReadError("");
    try { await apiRequest("/api/web-notifications/read", { through_id:data.items[0].id }, "POST"); window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT)); await refresh(); }
    catch { setReadError("Не удалось отметить уведомления прочитанными. Попробуйте ещё раз."); }
    finally { setReadBusy(false); }
  };
  const more = async () => {
    if (!data?.next_before || moreBusy) return;
    const sequence = ++requestSequence.current;
    setMoreBusy(true); setMoreError("");
    try { const page = await apiRequest<Inbox>("/api/web-notifications", { before:data.next_before, category }); if (sequence === requestSequence.current) setData({ ...page, items:[...data.items,...page.items] }); }
    catch { if (sequence === requestSequence.current) setMoreError("Не удалось загрузить историю. Попробуйте ещё раз."); }
    finally { setMoreBusy(false); }
  };
  const visibleItems = groupNotifications(data?.items || []);
  const pushAvailable = supported();
  const pushStatus = !pushAvailable ? 'Недоступны в этом браузере'
    : permission === 'denied' ? 'Заблокированы браузером'
    : subscribed ? 'Включены на этом устройстве'
    : !data ? error ? 'Не удалось проверить доступность' : 'Проверяем доступность…'
    : !data.push.enabled ? 'Пока недоступны' : 'Выключены';
  return <div className="notifications-page">
    <BackButton />
    <header className="notifications-header">
      <h1>Уведомления</h1>
      <p>Результаты, прогнозы и события гоночного уик-энда.</p>
    </header>
    <div className="notifications-layout">
      <section className="notifications-inbox" aria-labelledby="notifications-inbox-heading">
        <div className="notifications-inbox-heading">
          <h2 id="notifications-inbox-heading">История событий</h2>
          {data && <span className="notifications-unread-count" role="status">{data.unread ? `Непрочитанных: ${data.unread}` : 'Всё прочитано'}</span>}
        </div>
        <div className="notifications-toolbar">
          <div className="notifications-filter">
            <label htmlFor="notifications-category">Тип уведомлений</label>
            <CustomSelect id="notifications-category" ariaLabel="Тип уведомлений" value={category} onChange={value => { setData(null); setError(''); setReadError(''); setMoreError(''); setCategory(String(value)); }} options={[
              { value: 'all', label: 'Все' }, { value: 'results', label: 'Результаты' },
              { value: 'predictions', label: 'Прогнозы' }, { value: 'voting', label: 'Голосования' },
              { value: 'reminders', label: 'Напоминания' }, { value: 'admin', label: 'Системные' },
            ]} />
          </div>
          {data && <button type="button" className="notifications-read" disabled={!data.unread || readBusy || !data.items.length} onClick={markRead}
            title={data.items.length ? `Отметить все уведомления до ${new Date(data.items[0].created_at * 1000).toLocaleString('ru-RU')} включительно` : undefined}>
            {readBusy ? 'Отмечаем…' : 'Отметить прочитанными'}
          </button>}
        </div>
        {error && <div className="notifications-feedback" role="alert"><p>{error}</p><button type="button" className="notifications-button" onClick={() => void refresh()}>Повторить загрузку</button></div>}
        {readError && <p className="notifications-feedback" role="alert">{readError}</p>}
        {!data ? !error && <div className="notifications-loading" role="status"><HomeIcon name="history" /><p>Загружаем уведомления…</p></div> : <>
          {!data.items.length && <div className="notifications-empty">
            <HomeIcon name="notifications" />
            <h3>{category === 'all' ? 'Новых событий пока нет' : 'В этой категории пока нет событий'}</h3>
            <p>{category === 'all' ? 'Здесь появятся уведомления о гонках, прогнозах и голосованиях. Прошедшие события повторно не рассылаются.' : 'Выберите другой тип уведомлений или вернитесь позже.'}</p>
          </div>}
          {visibleItems.length < data.items.length && <p className="notifications-note notifications-group-note">Повторные сообщения объединены.</p>}
          <ul className="notifications-list">
            {visibleItems.map(item => {
              const clock = item.reminder ? reminderClock(item.reminder, now) : null;
              const presentation = notificationBody(item.body, item.url);
              const body = clock ? reminderBody(presentation.body) : presentation.body;
              const long = body.length > 320;
              const preview = long ? body.slice(0, 320).trimEnd() + '…' : body;
              return <li key={item.id}><article className={`notification-item${item.read_at ? '' : ' is-unread'}`}>
                <Link className="notification-destination" to={item.url}>
                  <div className="notification-meta">
                    <time dateTime={new Date(item.created_at * 1000).toISOString()}>{new Date(item.created_at * 1000).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', year: 'numeric' })}</time>
                    {!item.read_at && <span className="notification-new">Не прочитано</span>}
                  </div>
                  {item.priority && <span className={`notification-priority priority-${item.priority}`}>{priorityNames[item.priority]} приоритет</span>}
                  <h3>{clock ? 'Сессия уик-энда' : item.title}</h3>
                  {clock && <div className={`notification-clock phase-${clock.phase}`} aria-label="Статус сессии"><HomeIcon name="clock" /><strong>{clock.label}</strong>{clock.estimated && <small>По расписанию</small>}</div>}
                  <p className="notification-body">{preview}</p>
                  <span className="notification-open">{item.historical_snapshot ? 'Актуальный результат' : clock ? 'Расписание сессий' : 'Открыть'}<HomeIcon name="chevronRight" /></span>
                </Link>
                {long && <details className="notification-full"><summary>Показать сообщение целиком</summary><p className="notification-body">{body}</p></details>}
                {item.copies > 1 && <p className="notifications-note">Объединено сообщений: {item.copies}</p>}
                {presentation.uncertainPoints && <p className="notifications-warning">Очки в этом архивном сообщении не подтверждены. Проверьте актуальную классификацию по ссылке выше.</p>}
                {(item.historical_snapshot ?? /-results|^\/predictions|^\/voting/.test(item.url)) && <p className="notifications-note">Итог на момент отправки. После уточнения данных или пересчёта значения могли измениться.</p>}
              </article></li>;
            })}
          </ul>
          {moreError && <p className="notifications-feedback" role="alert">{moreError}</p>}
          {data.next_before && <button type="button" className="notifications-button notifications-more" disabled={moreBusy} onClick={more}>{moreBusy ? 'Загружаем историю…' : 'Показать ещё'}</button>}
        </>}
      </section>
      <aside className="notifications-controls" aria-labelledby="notifications-push-heading">
        <div className="notifications-push-heading"><HomeIcon name="notifications" /><h2 id="notifications-push-heading">Push на устройстве</h2></div>
        <p className={`notifications-push-status${subscribed ? ' is-enabled' : ''}`} role="status">{pushStatus}</p>
        <p>Новые события, даже когда сайт закрыт. История уведомлений сохраняется отдельно.</p>
        <button type="button" className={`notifications-button${subscribed ? '' : ' notifications-primary'}`} disabled={pushBusy || !pushAvailable || (!subscribed && !data?.push.enabled)} onClick={togglePush}>{pushBusy ? 'Сохраняем…' : subscribed ? 'Отключить push' : 'Включить push'}</button>
        {!pushAvailable ? <p className="notifications-note">В этом режиме браузера push недоступен. История уведомлений продолжает работать.</p>
          : data && !data.push.enabled && <p className="notifications-note">Push ещё не настроен на сервере.</p>}
        {pushError && <p className="notifications-feedback" role="alert">{pushError}</p>}
        {permission === 'denied' && <div className="notifications-help">
          <h3>Разрешите уведомления в браузере</h3>
          <p>На компьютере нажмите значок настроек слева от адреса f1hub.ru → «Разрешения для этого сайта» → «Уведомления» → «Разрешить». Затем обновите страницу.</p>
        </div>}
        {ios && !standalone && <div className="notifications-help">
          <h3>На iPhone нужно приложение</h3>
          <p>Откройте f1hub.ru в Safari → «Поделиться» → «На экран Домой» → «Добавить». Затем откройте TurboTears с новой иконки и вернитесь сюда.</p>
        </div>}
        {!ios && /Android/i.test(navigator.userAgent) && !standalone && <details className="notifications-install-guide">
          <summary>Как установить TurboTears</summary>
          <p>Chrome → меню ⋮ → Установить приложение или Добавить на главный экран.</p>
        </details>}
      </aside>
    </div>
  </div>;
}
