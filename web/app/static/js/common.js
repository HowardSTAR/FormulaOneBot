// web/app/static/js/common.js

function initTelegram() {
    if (!tg) {
        console.warn('Telegram WebApp недоступен');
        return false;
    }

    try {
        tg.ready();
        tg.expand(); // Разворачиваем на весь экран
        
        // Устанавливаем цвета хедера и фона, чтобы они совпадали с нашим CSS
        // (Черный #0b0d12)
        const bgColor = '#0b0d12'; 
        
        if (tg.setHeaderColor) {
            tg.setHeaderColor(bgColor);
        }
        if (tg.setBackgroundColor) {
            tg.setBackgroundColor(bgColor);
        }
        
        // Включаем подтверждение закрытия, если нужно
        tg.enableClosingConfirmation();
        
    } catch (e) {
        console.warn('Telegram WebApp init error', e);
    }

    return true;
}