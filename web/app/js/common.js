// Общая библиотека для работы с Telegram Mini App и API

const tg = window.Telegram?.WebApp || null;
const API_BASE = '/api';  // Для продакшена измени на полный URL

// Инициализация Telegram WebApp
function initTelegram() {
    if (!tg) {
        console.warn('Telegram WebApp недоступен');
        return false;
    }

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
    if (tg.themeParams?.bg_color) {
        document.body.style.backgroundColor = tg.themeParams.bg_color;
    }

    return true;
}

// Получение Telegram ID пользователя
function getTelegramId() {
    if (!tg?.initDataUnsafe?.user) {
        return null;
    }
    return tg.initDataUnsafe.user.id;
}

// Получение информации о пользователе
function getUserInfo() {
    if (!tg?.initDataUnsafe?.user) {
        return null;
    }
    return tg.initDataUnsafe.user;
}

// Отправка данных обратно в бота
function sendAction(action, data = {}) {
    if (!tg) return;

    const payload = {
        type: 'miniapp_action',
        action,
        ...data,
        ts: Date.now(),
    };

    try {
        tg.sendData(JSON.stringify(payload));
    } catch (e) {
        console.error('Ошибка при отправке данных из MiniApp:', e);
    }
}

// API запросы
async function apiRequest(endpoint, params = {}) {
    const url = new URL(`${API_BASE}${endpoint}`, window.location.origin);
    
    // Добавляем параметры
    Object.entries(params).forEach(([key, value]) => {
        if (value !== null && value !== undefined) {
            url.searchParams.append(key, value.toString());
        }
    });

    // Добавляем telegram_id если доступен
    const telegramId = getTelegramId();
    if (telegramId) {
        url.searchParams.append('telegram_id', telegramId.toString());
    }

    try {
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`API request failed: ${endpoint}`, error);
        throw error;
    }
}

// Форматирование даты
function formatDate(dateString) {
    if (!dateString) return '';
    
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
        });
    } catch (e) {
        return dateString;
    }
}

// Форматирование времени
function formatTime(dateString) {
    if (!dateString) return '';
    
    try {
        const date = new Date(dateString);
        return date.toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch (e) {
        return dateString;
    }
}

// Показать загрузку
function showLoading(container, message = 'Загрузка...') {
    if (typeof container === 'string') {
        container = document.getElementById(container);
    }
    
    if (!container) return;
    
    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <p>${message}</p>
        </div>
    `;
}

// Показать ошибку
function showError(container, message) {
    if (typeof container === 'string') {
        container = document.getElementById(container);
    }
    
    if (!container) return;
    
    container.innerHTML = `
        <div class="error">
            ❌ ${message}
        </div>
    `;
}

// Показать пустое состояние
function showEmpty(container, message, icon = '📭') {
    if (typeof container === 'string') {
        container = document.getElementById(container);
    }
    
    if (!container) return;
    
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">${icon}</div>
            <p>${message}</p>
        </div>
    `;
}

// Форматирование очков
function formatPoints(points) {
    if (points === null || points === undefined) return '—';
    const num = parseFloat(points);
    if (isNaN(num)) return '—';
    return `${Math.floor(num)} очк.`;
}

// Форматирование позиции
function formatPosition(position) {
    if (position === null || position === undefined) return '—';
    const num = parseInt(position);
    if (isNaN(num)) return '—';
    return `${num}`;
}

// Получить эмодзи для позиции
function getPositionEmoji(position) {
    if (position === 1) return '🥇';
    if (position === 2) return '🥈';
    if (position === 3) return '🥉';
    return '';
}

// Инициализация кнопки "Назад"
function initBackButton(target = '/') {
    const backBtn = document.getElementById('btn-back-home');
    if (backBtn) {
        // Удаляем старые обработчики, если они есть
        const newBtn = backBtn.cloneNode(true);
        backBtn.parentNode.replaceChild(newBtn, backBtn);
        
        // Добавляем новый обработчик
        newBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            window.location.href = target;
        });
        
        // Также добавляем обработчик для touch событий (для мобильных)
        newBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            e.stopPropagation();
            window.location.href = target;
        });
    }
}

// Инициализация всех кнопок с data-action
function initActionButtons() {
    document.querySelectorAll('.btn[data-action]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const action = btn.dataset.action;
            sendAction(action);
            if (tg) {
                tg.close();
            }
        });
    });
}

// Экспорт для использования в других файлах
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        tg,
        initTelegram,
        getTelegramId,
        getUserInfo,
        sendAction,
        apiRequest,
        formatDate,
        formatTime,
        formatPoints,
        formatPosition,
        getPositionEmoji,
        showLoading,
        showError,
        showEmpty,
        initBackButton,
        initActionButtons,
    };
}
