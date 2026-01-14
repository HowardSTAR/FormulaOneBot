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

/* --- ЛОГИКА СВАЙПА "НАЗАД" --- */
document.addEventListener('DOMContentLoaded', () => {
    // Не включаем свайп на главной странице
    if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
        return;
    }

    let touchStartX = 0;
    let touchStartY = 0;

    // 1. Начало касания
    document.addEventListener('touchstart', function(event) {
        touchStartX = event.changedTouches[0].screenX;
        touchStartY = event.changedTouches[0].screenY;
    }, false);

    // 2. Конец касания
    document.addEventListener('touchend', function(event) {
        let touchEndX = event.changedTouches[0].screenX;
        let touchEndY = event.changedTouches[0].screenY;

        handleSwipeGesture(touchStartX, touchStartY, touchEndX, touchEndY);
    }, false);
});

function handleSwipeGesture(startX, startY, endX, endY) {
    // Вычисляем разницу
    const xDiff = endX - startX;
    const yDiff = Math.abs(endY - startY);

    // УСЛОВИЯ СВАЙПА:
    // 1. Жест начался с левого края экрана (первые 50px) - как в iOS
    const isFromEdge = startX < 50;

    // 2. Движение вправо (xDiff > 0) и достаточно длинное (> 60px)
    const isSwipeRight = xDiff > 60;

    // 3. Движение было горизонтальным, а не вертикальным (чтобы не путать со скроллом)
    const isHorizontal = xDiff > (yDiff * 2);

    if (isFromEdge && isSwipeRight && isHorizontal) {
        // Визуальный эффект (опционально): можно добавить анимацию выезда
        // Но пока просто переходим назад
        goBack();
    }
}

// Универсальная функция назад
function goBack() {
    // Если есть кнопка "Назад" с href, используем её ссылку
    const backBtn = document.querySelector('.btn-back');
    if (backBtn && backBtn.getAttribute('href')) {
        window.location.href = backBtn.getAttribute('href');
    } else {
        // Иначе просто на главную
        window.location.href = 'index.html';
    }
}