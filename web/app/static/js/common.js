// 1. Инициализация переменных
const API_BASE = '';
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
        const bgColor = '#0b0d12';
        if (tg.setHeaderColor) tg.setHeaderColor(bgColor);
        if (tg.setBackgroundColor) tg.setBackgroundColor(bgColor);
    } catch (e) {
        console.warn('Telegram WebApp init error', e);
    }
    return true;
}

function getUserInfo() {
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        return tg.initDataUnsafe.user;
    }
    return null;
}

function getInitData() {
    return tg?.initData || '';
}

// 5. Главная функция запросов к API
// 👇 ИЗМЕНЕНИЕ: Добавили аргумент method и логику для POST
async function apiRequest(endpoint, params = {}, method = 'GET') {
    const url = new URL(API_BASE + endpoint, window.location.origin);

    const headers = {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': getInitData()
    };

    const options = {
        method: method,
        headers: headers
    };

    // Если GET — параметры в URL
    if (method.toUpperCase() === 'GET') {
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.append(key, params[key]);
            }
        });
    }
    // Если POST/PUT — параметры в Body как JSON
    else {
        options.body = JSON.stringify(params);
    }

    console.log(`Fetching: ${url.toString()} [${method}]`);

    try {
        const response = await fetch(url, options);

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
    if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
        return;
    }

    let touchStartX = 0;
    let touchStartY = 0;

    document.addEventListener('touchstart', function(event) {
        touchStartX = event.changedTouches[0].screenX;
        touchStartY = event.changedTouches[0].screenY;
    }, false);

    document.addEventListener('touchend', function(event) {
        let touchEndX = event.changedTouches[0].screenX;
        let touchEndY = event.changedTouches[0].screenY;
        handleSwipeGesture(touchStartX, touchStartY, touchEndX, touchEndY);
    }, false);
});

function handleSwipeGesture(startX, startY, endX, endY) {
    const xDiff = endX - startX;
    const yDiff = Math.abs(endY - startY);
    const isFromEdge = startX < 50;
    const isSwipeRight = xDiff > 60;
    const isHorizontal = xDiff > (yDiff * 2);

    if (isFromEdge && isSwipeRight && isHorizontal) {
        goBack();
    }
}

function goBack() {
    const backBtn = document.querySelector('.btn-back');
    if (backBtn && backBtn.getAttribute('href')) {
        window.location.href = backBtn.getAttribute('href');
    } else {
        window.location.href = 'index.html';
    }
}