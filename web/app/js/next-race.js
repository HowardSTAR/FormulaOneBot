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
    
    let html = `
      <p style="font-weight: 600; font-size: 16px; margin-top: 8px;">
        ${data.round.toString().padStart(2, '0')}. ${data.event_name}
      </p>
      <p style="color: var(--text-muted); font-size: 14px; margin-top: 4px;">
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