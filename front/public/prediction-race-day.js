/* Shared deadline notice for both preserved and preview frontends. */
(() => {
  let state = null;
  let offset = 0;
  let notice = null;
  let wasOpen = false;
  let fetching = false;
  let lastPath = location.pathname;
  const onPage = () => /^\/predictions\/?$/.test(location.pathname);
  const timeLabel = value => new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value)) + ' МСК';

  function render() {
    if (lastPath !== location.pathname) {
      lastPath = location.pathname;
      state = null; wasOpen = false;
      void refresh();
    }
    const main = document.querySelector('main.predictions-page');
    if (!onPage() || !main || !state?.race_day_exception) {
      notice?.remove(); notice = null; return;
    }
    if (!notice?.isConnected) {
      notice = document.createElement('aside');
      notice.className = 'prediction-race-day-notice';
      notice.setAttribute('aria-label', 'Срок приёма прогнозов на сегодняшнюю гонку');
      const title = document.createElement('strong'); title.dataset.part = 'title';
      const detail = document.createElement('p'); detail.dataset.part = 'detail';
      const timer = document.createElement('div'); timer.className = 'prediction-race-day-timer';
      const label = document.createElement('span'); label.textContent = 'До старта гонки и закрытия прогнозов';
      const output = document.createElement('output'); output.dataset.part = 'clock';
      output.setAttribute('role', 'timer'); output.setAttribute('aria-live', 'off');
      timer.append(label, output); notice.append(title, detail, timer);
      const hero = main.querySelector('.predictions-hero');
      hero ? hero.after(notice) : main.prepend(notice);
    }
    const seconds = Math.max(0, Math.ceil((Date.parse(state.deadline_utc) - Date.now() - offset) / 1000));
    const open = state.is_open && seconds > 0;
    const title = notice.querySelector('[data-part=title]');
    const detail = notice.querySelector('[data-part=detail]');
    const clock = notice.querySelector('[data-part=clock]');
    const text = open ? 'Сегодня прогнозы открыты до старта гонки' : 'Приём прогнозов на эту гонку закрыт';
    if (title.textContent !== text) title.textContent = text;
    const explanation = `Разовое исключение для этого этапа: до ${timeLabel(state.deadline_utc)}. После старта отправка и изменения недоступны.`;
    if (detail.textContent !== explanation) detail.textContent = explanation;
    const digits = [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
      .map(n => String(n).padStart(2, '0')).join(':');
    if (clock.textContent !== digits) clock.textContent = digits;
    if (wasOpen && !open) {
      wasOpen = false;
      // Refresh the React form once at its server-authoritative boundary.
      location.reload();
    } else if (open) wasOpen = true;
  }

  async function refresh() {
    if (!onPage() || fetching) return;
    fetching = true;
    try {
      const response = await fetch('/api/predictions/window', {cache: 'no-store'});
      if (!response.ok) return;
      state = await response.json();
      offset = Date.parse(state.server_now_utc) - Date.now();
      render();
    } catch { /* Existing prediction form retains its own errors and deadline checks. */ }
    finally { fetching = false; }
  }
  new MutationObserver(render).observe(document.body, {childList: true, subtree: true});
  window.addEventListener('popstate', () => { void refresh(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void refresh(); });
  setInterval(render, 1000);
  setInterval(() => { void refresh(); }, 15000);
  void refresh();
})();
