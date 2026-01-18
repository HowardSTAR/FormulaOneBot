let currentRaceData = null;

async function loadNextRaceInfo() {
  const container = document.getElementById('race-content');
  const actionsCard = document.getElementById('race-actions');

  showLoading(container, 'Загружаю ближайший этап…');

  try {
    const data = await apiRequest('/next-race');

    if (data.status === 'no_schedule') {
      showError(container, `Нет расписания для сезона ${data.season}`);
      return;
    }

    if (data.status === 'season_finished') {
      showEmpty(container, `Сезон ${data.season} уже завершён ✅`, '🏁');
      return;
    }

    // Обычный случай — status === 'ok'
    currentRaceData = data;
    
    // [NEW] Формируем путь к карте.
    // encodeURIComponent нужен на случай спецсимволов, но обычно для .svg имен достаточно простого подставления.
    // Название файла должно точно совпадать с data.event_name (например "Bahrain Grand Prix.svg")
    const trackImage = `/assets/circuit/${data.event_name}.svg`;

    let html = `
      <p style="font-weight: 600; font-size: 16px; margin-top: 8px;">
        ${data.round.toString().padStart(2, '0')}. ${data.event_name}
      </p>

      <div class="track-map-container" style="margin: 12px 0; text-align: center; min-height: 100px; display: flex; align-items: center; justify-content: center;">
          <img 
            src="${trackImage}" 
            class="track-map-img" 
            style="max-width: 100%; height: auto; max-height: 150px;"
            alt="Track Map"
            onerror="this.style.display='none'; this.nextElementSibling.style.display='block'"
          >
          <div class="no-map-placeholder" style="display:none; font-size: 48px;">🏎️</div>
      </div>

      <p style="color: font-size: 14px; margin-top: 4px;">
        📍 ${data.country}, ${data.location}
      </p>
    `;

    if (data.utc && data.local) {
      html += `
        <p style="margin-top: 10px; font-size: 14px;">
          ⏰ Старт гонки:<br>
          • ${data.utc}<br>
          • ${data.local}
        </p>
      `;
    } else if (data.date) {
      html += `<p style="margin-top: 10px; font-size: 14px;">📅 Дата: ${data.date}</p>`;
    }

    container.innerHTML = html;

    // Показываем кнопки действий
    if (actionsCard) {
      actionsCard.style.display = 'block';
      
      // Настройка кнопки расписания
      const scheduleBtn = document.getElementById('btn-schedule');
      if (scheduleBtn && data.round) {
        scheduleBtn.addEventListener('click', () => {
          window.location.href = `weekend-schedule.html?season=${data.season}&round=${data.round}`;
        });
      }
    }
  } catch (e) {
    console.error(e);
    showError(container, 'Не удалось получить данные о ближайшей гонке 😔');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initTelegram();
  initBackButton('/');
  loadNextRaceInfo();
});