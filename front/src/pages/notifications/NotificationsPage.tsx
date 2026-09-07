import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { BackButton } from "../../components/BackButton";
import "./notifications.css";

type Item = { id: number; title: string; body: string; url: string; created_at: number; read_at: number | null };
type Inbox = { items: Item[]; unread: number; next_before: number | null; push: { enabled: boolean; public_key: string } };
function keyBytes(key: string) {
  const value = atob(key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4-key.length%4)%4));
  return Uint8Array.from(value, char => char.charCodeAt(0));
}
const supported = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export default function NotificationsPage() {
  const [data, setData] = useState<Inbox | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [subscribed, setSubscribed] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    supported() ? Notification.permission : "unsupported",
  );
  const standalone = window.matchMedia("(display-mode: standalone)").matches
    || !!(navigator as Navigator & { standalone?: boolean }).standalone;
  const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent)
    || (/Macintosh/i.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  const refresh = useCallback(async () => {
    try { setData(await apiRequest<Inbox>("/api/web-notifications")); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось загрузить уведомления"); }
  }, []);
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
    if (!supported()) return;
    setBusy(true); setError("");
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
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось изменить подписку"); }
    finally { setBusy(false); }
  };
  const markRead = async () => {
    if (!data?.items.length) return;
    try { await apiRequest("/api/web-notifications/read", { through_id:data.items[0].id }, "POST"); await refresh(); }
    catch { setError("Не удалось отметить уведомления прочитанными"); }
  };
  const more = async () => {
    if (!data?.next_before) return;
    setBusy(true);
    try { const page = await apiRequest<Inbox>("/api/web-notifications", { before:data.next_before }); setData({ ...page, items:[...data.items,...page.items] }); }
    catch { setError("Не удалось загрузить историю"); }
    finally { setBusy(false); }
  };
  return <div className="notifications-page">
    <BackButton /><header><small>TURBOTEARS · ЛИЧНОЕ</small><h1>Уведомления</h1>
      <p>Результаты, прогнозы, голосования и новости сессий. Избранные пилоты и команды выделяются в итогах.</p></header>
    <section className="notifications-controls">
      <strong>Push на этом устройстве</strong>
      <p>Только новые события, даже когда сайт закрыт. История сохраняется отдельно. На iPhone сначала добавьте сайт на экран «Домой».</p>
      <button disabled={busy || !supported() || (!subscribed && !data?.push.enabled)} onClick={togglePush}>{subscribed ? "Отключить push" : "Включить push"}</button>
      {!supported() ? <p>В этом режиме браузера push недоступен. История уведомлений продолжает работать.</p>
        : data && !data.push.enabled && <p>Push ещё не настроен на сервере.</p>}
      {permission === "denied" && <div className="notifications-help" role="status">
        <strong>Уведомления заблокированы браузером</strong>
        <p>На компьютере нажмите значок настроек слева от адреса f1hub.ru → «Разрешения для этого сайта» → «Уведомления» → «Разрешить». Затем обновите страницу.</p>
      </div>}
      {ios && !standalone && <div className="notifications-help">
        <strong>Сначала установите приложение на iPhone</strong>
        <p>Откройте f1hub.ru именно в Safari → «Поделиться» → «На экран Домой» → «Добавить». Затем откройте TurboTears с новой иконки и вернитесь сюда.</p>
      </div>}
      {(ios || /Android/i.test(navigator.userAgent)) && !standalone && <details className="notifications-install-guide">
        <summary>Как установить TurboTears на телефон</summary>
        <p>{ios ? "Safari → Поделиться → На экран Домой → Добавить." : "Chrome → меню ⋮ → Установить приложение или Добавить на главный экран."}</p>
      </details>}
    </section>
    {error && <p role="alert">{error}</p>}
    {!data ? <p>Загружаем уведомления…</p> : <>
      <div className="notifications-toolbar"><span>Непрочитанных: {data.unread}</span><button disabled={!data.unread} onClick={markRead}>Прочитать все</button></div>
      {!data.items.length && <p className="notifications-empty">Здесь появятся новые события. Прошедшие уведомления не рассылаются повторно.</p>}
      {data.items.map(item => <article key={item.id} className={item.read_at ? "" : "is-unread"}>
        <time>{new Date(item.created_at*1000).toLocaleString("ru-RU")}</time><h2>{item.title}</h2><p>{item.body}</p>
        <Link to={item.url}>Открыть →</Link>
      </article>)}
      {data.next_before && <button disabled={busy} onClick={more}>Показать ещё</button>}
    </>}
  </div>;
}
