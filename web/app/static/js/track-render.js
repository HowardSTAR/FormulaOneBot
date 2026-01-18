/**
 * Библиотека для отрисовки трасс F1 в формате SVG
 * Файл: web/app/static/js/track-render.js
 */

const TrackRenderer = {
    // Конфигурация стилей
    config: {
        strokeColor: '#e10600', // Основной красный цвет (var(--primary))
        strokeWidth: 3,
        fillColor: 'none',
        bgColor: 'rgba(255, 255, 255, 0.05)',
        viewBox: "0 0 500 500" // Базовый размер холста
    },

    // База данных путей (SVG Path Data).
    // Сюда нужно добавить реальные пути для каждой трассы.
    // Можно взять SVG с Википедии, открыть в редакторе и скопировать атрибут d=""
    paths: {
        // Пример: Просто овал (для теста)
        "test_track": "M 100,250 A 150,150 0 1,1 400,250 A 150,150 0 1,1 100,250",
        
        // Пример: Силуэт похожий на Бахрейн (упрощенно)
        "bahrain": "M 380,350 L 150,350 L 100,250 L 150,150 L 300,150 L 350,200 L 400,100 L 450,150 L 450,300 Z",
        
        // Пример: Силуэт похожий на Монцу
        "monza": "M 150,400 L 350,400 L 400,300 L 400,100 L 350,50 L 150,50 L 100,150 L 100,350 Z",
        
        // Заглушка, если трассы нет в базе
        "default": "M 100,100 L 400,100 L 400,400 L 100,400 Z" 
    },

    /**
     * Главная функция отрисовки
     * @param {string} containerId - ID HTML элемента, куда рисовать
     * @param {string} circuitKey - Ключ трассы (например, 'bahrain')
     */
    draw: function(containerId, circuitKey) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // Нормализуем ключ (в нижний регистр)
        const key = circuitKey ? circuitKey.toLowerCase() : 'default';
        
        // Берем путь или дефолтный, если такого нет
        const pathData = this.paths[key] || this.paths['default'];

        // Формируем SVG
        const svgHTML = `
            <svg viewBox="${this.config.viewBox}" 
                 style="width: 100%; height: 100%; filter: drop-shadow(0 0 5px rgba(225,6,0,0.5));">
                
                <path d="${pathData}" 
                      stroke="${this.config.strokeColor}" 
                      stroke-width="${this.config.strokeWidth}" 
                      fill="${this.config.fillColor}"
                      stroke-linecap="round" 
                      stroke-linejoin="round"
                      class="track-animation" />
            </svg>
        `;

        container.innerHTML = svgHTML;
        
        // Если трассы нет в базе, можно вывести консоль, чтобы знать, что добавить
        if (!this.paths[key]) {
            console.warn(`Track path for "${key}" not found. Using default.`);
            // Опционально: показать текст "Нет схемы" поверх
        }
    }
};