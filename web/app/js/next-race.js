const tg = window.Telegram.WebApp || null;

function initTelegram() {
  if (!tg) return;

  try {
    tg.ready();
  } catch (e) {
    console.warn('Telegram WebApp ready() error', e);
  }

  try {
    tg.expand();
  } catch (e) {
    console.warn('Telegram WebApp expand() error', e);
  }

  // Подстройка фона под тему Telegram
  if (tg.themeParams && tg.themeParams.bg_color) {
    document.body.style.backgroundColor = tg.themeParams.bg_color;
  }
}

async function loadNextRaceInfo() {
  const titleEl = document.getElementById('nr-title');
  const locationEl = document.getElementById('nr-location');
  const timeEl = document.getElementById('nr-time');

  if (!titleEl || !locationEl || !timeEl) {
    console.error('Элементы для вывода ближайшей гонки не найдены в DOM');
    return;
  }

  titleEl.textContent = 'Загружаю ближайший этап…';
  locationEl.textContent = '';
  timeEl.textContent = '';

  try {
    // Если backend (FastAPI) на том же домене:
    // const resp = await fetch('/api/next-race');

    // Если backend на другом домене (ngrok / сервер) – укажи ПОЛНЫЙ URL:
    const resp = await fetch('/api/next-race');

    if (!resp.ok) {
      throw new Error('HTTP ' + resp.status);
    }

    const data = await resp.json();

    if (data.status === 'no_schedule') {
      titleEl.textContent = `Нет расписания для сезона ${data.season}`;
      return;
    }

    if (data.status === 'season_finished') {
      titleEl.textContent = `Сезон ${data.season} уже завершён ✅`;
      locationEl.textContent = '';
      timeEl.textContent = '';
      return;
    }

    // Обычный случай — status === 'ok'
    titleEl.textContent = `${data.round}. ${data.event_name} (сезон ${data.season})`;
    locationEl.textContent = `📍 ${data.country}, ${data.location}`;

    if (data.utc && data.local) {
      timeEl.innerHTML =
        '⏰ Старт гонки:<br>' +
        `• ${data.utc}<br>` +
        `• ${data.local}`;
    } else if (data.date) {
      timeEl.textContent = `📅 Дата: ${data.date}`;
    } else {
      timeEl.textContent = '';
    }
  } catch (e) {
    console.error(e);
    titleEl.textContent = 'Не удалось получить данные о ближайшей гонке 😔';
    locationEl.textContent = '';
    timeEl.textContent = 'Попробуй ещё раз чуть позже.';
  }
}

function sendAction(action) {
  if (!tg) return;

  const payload = {
    type: 'miniapp_action',
    action,
    ts: Date.now(),
  };

  try {
    tg.sendData(JSON.stringify(payload));
  } catch (e) {
    console.error('Ошибка при отправке данных из MiniApp:', e);
  }
}

function initButtons() {
  // Кнопки расписание / квалификация / гонка
  document.querySelectorAll('.btn[data-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;
      sendAction(action);
      if (tg) {
        tg.close();
      }
    });
  });

  // Назад на главную страницу mini-app
  const backBtn = document.getElementById('btn-back-home');
  if (backBtn) {
    backBtn.addEventListener('click', () => {
      window.location.href = 'index.html';
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initTelegram();
  initButtons();
  loadNextRaceInfo();
});