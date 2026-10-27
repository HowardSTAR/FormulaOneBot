# Ошибка открытия страницы TurboTears

## Задача и композиция

Экран `RouteErrorPage` помогает восстановить открытие страницы после ошибки маршрута
или загрузки модуля. Он может заменить всю оболочку, поэтому сам содержит бренд и
существующий переключатель темы. Основное действие — «Повторить загрузку», второе —
«На главную». Авторизация и сетевые данные для отображения не нужны.

На телефоне текст и действия расположены перед графикой; на десктопе графика справа.
Это один адаптивный DOM, без карточки вокруг сообщения и без минимальной высоты
содержимого. Использованы принятые токены обеих тем, Inter / Space Grotesk, спокойный
фон и функциональный стеклянный контрол темы.

Графика — объёмная сцена короткого пит-стопа: красный болид на переднем домкрате
и снятое колесо рядом. Это иллюстрация, а не конкретная машина или гоночные данные.
Прозрачный фон и мягкие края работают в обеих темах. Декорация скрыта от скринридера.
Старая схема и декоративный знак обновления полностью удалены; знак остался на кнопке.
Заголовок и сообщение доступны отдельно от кнопок; ошибка объявляется через alert.
Клавиатурный порядок: главная по бренду, тема, повтор, ссылка на главную.

## Восстановление

Повтор использует прежний `window.location.reload()` и сохраняет путь, параметры и
hash. Переход на главную — обычная ссылка, полностью перезапускающая приложение;
это позволяет выйти из состояния ошибки маршрута. Поддерживается Cmd/Ctrl-click.
Сообщения исключений и внутренние пути в интерфейс не выводятся.

404 сохраняет собственный текст и действия на главную / в календарь. Тот же компонент
используется внутри существующей оболочки для неизвестных адресов и самостоятельно
для 404, полученной обработчиком ошибки. Старый стиль `ui-not-found` удалён; локальный
экран исключён из принудительно тёмной оболочки legacy-страниц.

## Проверка

Изолированный fixture: `/tests/route-error-preview.html?theme=light|dark`.
`state=not-found` даёт 404, `state=chunk` моделирует ошибку загрузки модуля,
`retry=success` позволяет проверить успешную повторную загрузку. Production API,
личные данные и реальные ошибки для этого не используются.

`scripts/check-route-error-design.cjs` проверяет:

- обе темы, ошибки и 404 на 320, 390, 759, 760, 1440 px;
- текст 200% на телефоне и десктопе, отсутствие горизонтального переполнения;
- клавиатуру, видимый фокус и высоту кнопок не менее 44 px;
- скрытие диагностических подробностей, действия восстановления;
- сохранение полного URL при повторе и сохранение ручной темы после перезагрузки.

Проверки прошли; мобильные и десктопные изображения обеих тем осмотрены.
Типизация, lint и frontend-сборка прошли. Сборка сохраняет прежнее предупреждение
о крупных чанках. Impeccable scan отметил только распространённые шрифты — они
сознательно сохранены согласно продуктовому скиллу TurboTears.

Полный аудит скринридером и воспроизведение реальной production-аварии не выполнялись.
Push и публикация не выполнялись.


## Иллюстрация пит-стопа

Источник: встроенный `imagegen`, новый рисунок без изображений-референсов.
Рабочий ассет: `front/src/assets/illustrations/recovery-pit-stop.webp`, 1152 × 768,
около 162 КБ. Прозрачность сохранена при оптимизации через cwebp; пропорции сохранены.
Оригинал генерации остаётся в каталоге generated_images Codex.

Финальный промпт:

> Use case: stylized-concept. Asset type: transparent cutout illustration for a Formula 1 fan website error recovery screen, TurboTears. Create a polished, premium 3D editorial illustration of a brief pit-stop pause: a single compact generic unbranded red open-wheel racing car viewed from a clean elevated front three-quarter angle, its front nose clearly visible, supported by one small red front racing jack, with a single detached black slick racing wheel standing neatly nearby. All objects form one balanced compact composition. The car is stationary and intact, not crashed or damaged. Sleek sculptural red bodywork, dark graphite carbon parts, realistic broad black rubber slick tires, subtle silver mechanical details. Studio-quality product render, precise physically coherent geometry, restrained materials with soft highlights, calm reassuring mood. Actual transparent background with a very soft minimal contact shadow; no ground plane rectangle, no room, no backdrop. Landscape composition about 3:2, entire silhouette fully inside frame with about 8 percent breathing room, no cropping, visually centered and fills most of image. Readable at a displayed width of 360–520 pixels. No people, no text, no words, no logos, no numbers, no arrows, no refresh icons, no buttons, no UI, no podium, no traffic lights, no isolated extra tools, no sparkles, no cartoon face, no watermark. This is a still image, not an animation.
