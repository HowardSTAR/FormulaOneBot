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