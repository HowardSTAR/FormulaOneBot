// web/app/static/js/common.js

// 1. Инициализация переменных
const API_BASE = ''; // Оставляем пустым, чтобы запросы шли на тот же домен (localhost:8000)
const tg = window.Telegram?.WebApp;

// 2. Инициализация WebApp
function initTelegram() {
    if (!tg) {
        console.warn('Telegram WebApp недоступен (открыто в браузере?)');
        return false;
    }

    try {
        tg.ready();
        tg.expand();

        // Устанавливаем цвета под тему (Dark Mode)
        const bgColor = '#0b0d12';
        if (tg.setHeaderColor) tg.setHeaderColor(bgColor);
        if (tg.setBackgroundColor) tg.setBackgroundColor(bgColor);

    } catch (e) {
        console.warn('Telegram WebApp init error', e);
    }
    return true;
}

// 3. Получение данных пользователя
function getUserInfo() {
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        return tg.initDataUnsafe.user;
    }
    return null;
}

// 4. Получение строки авторизации (initData)
function getInitData() {
    return tg?.initData || '';
}

// 5. Главная функция запросов к API
async function apiRequest(endpoint, params = {}) {
    // Формируем полный URL (например: http://127.0.0.1:8000/api/next-race)
    const url = new URL(API_BASE + endpoint, window.location.origin);

    // Добавляем GET параметры (?season=2025&round=...)
    Object.keys(params).forEach(key => {
        if (params[key] !== null && params[key] !== undefined) {
            url.searchParams.append(key, params[key]);
        }
    });

    console.log(`Fetching: ${url.toString()}`); // Лог для отладки

    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                // Передаем подпись для защиты
                'X-Telegram-Init-Data': getInitData()
            }
        });

        if (!response.ok) {
            console.error(`API Error: ${response.status} ${response.statusText}`);
            throw new Error(`Server Error: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('Fetch failed:', error);
        throw error;
    }
}