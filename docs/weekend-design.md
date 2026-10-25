# «Уик-энд» и общая тема

Работа продолжается в `feature/new_design` по Apple Design Skill и с целевыми
требованиями WCAG 2.2 AA. Правила для следующих интерфейсных изменений закреплены
в `front/AGENTS.md`.

Общая палитра и оформление навигации вынесены из главной в
`front/src/assets/design-system.css`. На десктопе переключатель темы находится
справа над содержимым, на телефоне — в верхней панели рядом с аккаунтом.
На самых узких экранах остаётся кнопка со значком и доступным названием.
Первоначально учитывается системная тема. Ручной выбор сохраняется в
`turbotears-theme`, переживает перезагрузку, применяется при переходах и
синхронизируется между вкладками. Если хранилище недоступно, переключение
продолжает работать в текущей вкладке.

Ручной переключатель добавлен по прямому пожеланию пользователя. Это осознанное
отступление от общего совета HIG о системном выборе темы. Смысл рекомендации —
не заставлять человека настраивать каждое приложение — сохранён исходной
поддержкой системной темы до ручного выбора.

Экран «Уик-энд» использует одну адаптивную разметку. Сначала показаны этап и
старт гонки, затем расписание, результаты и сведения о трассе. Схема раскрывается
в нативном dialog с закрытием по Escape и возвратом фокуса. Факты раскрываются
элементами details/summary. Дата гонки доступна сразу, независимо от анимации.
Отдельная мобильная разметка и её старый CSS удалены.

Сохранены выбор архивного этапа через season/round, выгрузка всех сессий в
календарь, ссылки на классификацию и справочные подсказки. Ссылки на результаты
показываются для сессий, уже начавшихся по расписанию; это не утверждение о
фактическом окончании сессии или публикации результата. Сессии без точного
времени остаются в расписании с явной подписью. Отмена исключает скачивание
календаря и ссылки на результаты. Ошибка расписания не скрывает сведения об
этапе и карту. Все даты отображаются в выбранном часовом поясе.

Новая палитра имеет контраст вторичного текста 5.73:1 / 7.54:1 на светлой /
тёмной карточке. Кнопки имеют зоны нажатия от 44px, видимый фокус и подписи.
Запрет пользовательского масштабирования в index.html удалён. Предусмотрены
перенос текста, reduced motion, контрастные режимы и непрозрачный фон диалога.
Техническая подробная схема сохраняет тёмный холст для читаемости секторов.

Главная, «Уик-энд» и общая навигация используют новую тему. Содержимое остальных
экранов пока сохраняет читаемые старые поверхности и будет переходить на новые
компоненты при последующей работе. Полный аудит всех маршрутов не заявляется.

## Предпросмотр

Запустить `npm run dev` из `front/`, затем открыть:

`/tests/home-design-preview.html?page=weekend`

Тема переключается настоящей кнопкой. `theme=light` или `theme=dark` задаёт
первоначальное предпочтение только при отсутствии сохранённого выбора.
Параметры `state=empty`, `state=error`, `state=cancelled`, `state=finished`,
`state=schedule-error`, `state=untimed`, `state=past` проверяют состояния экрана.
`season=1997&round=4` проверяет открытие архива, `scale=2` — увеличение текста.
Данные вымышлены; демонстрация использует реальные компоненты, но не backend.

Автоматические проверки: фронтенд-тесты, ESLint, TypeScript, production-сборка и
бюджет начальной загрузки. Новые тесты проверяют выбор и сохранение темы,
недоступное хранилище, архивные параметры, неполные даты и маршруты результатов.
Визуальная проверка: обе темы, 320/390/820/1440px, текст 200%, диалог карты,
фокус, переходы и состояния загрузки/ошибок.

Полное соответствие WCAG требует отдельного ручного аудита, в том числе
реальным скринридером. Проверки здесь относятся к изменённым сценариям.

## Организация по визуальным примерам — 25 октября 2026

Страница состоит из сводки этапа и расписания. Сводка объединяет название,
место, номер этапа, диапазон дат, длину круга, число кругов и дистанцию с реальной
схемой трассы. Старт гонки остаётся виден компактной строкой. На телефоне
характеристики и карта соседствуют; при крупном тексте группы переходят в один
столбец. Цвета и Space Grotesk сохранены из главной TurboTears.

«Статистика трассы» открывает существующий нативный dialog карты с полными
характеристиками и раскрываемыми фактами. Проверенные схемы сохраняют секторы,
повороты и управления слоями. Для неподтверждённой конфигурации остаётся честный
контур и пояснение. Для COTA 2026 составы шин, семь оценок Pirelli и исторические рекорды
добавлены из официальных источников; сведения привязаны к сезону.

Начавшиеся сессии в расписании являются настоящими ссылками на классификацию
внутри уик-энда: `/next-race?season=2026&round=19&session=fp2`. Это сохраняет
Cmd/Ctrl-click, прямое открытие и историю. Сессия выбирается доступным общим
CustomSelect; будущие и не имеющие времени варианты недоступны. Строки результата
показывают позицию, пилота, команду и доступные время, отставание, круги и очки.
У всех пилотов одинаковые колонки; отсутствие значения показано прочерком,
нулевые круги и очки сохраняются. Профиль пилота остаётся ссылкой. Возврат
к расписанию фокусирует заголовок; исходные страницы классификаций доступны
по ссылке с сохранёнными сезоном, этапом и номером практики.

Запрашиваются существующие API результатов, без изменения backend. Ответ
проверяется по сезону, этапу и номеру практики: fallback предыдущего этапа
не показывается под заголовком выбранного. Загрузка, ошибка с повтором и пустая
классификация имеют отдельные состояния. Итоговый API квалификации не содержит
времён всех Q1/Q2/Q3, поэтому фиктивного переключения этих сегментов нет.

Проверены обе темы для сводки и результатов на 320/390/699/700/899/900/1440/1920 px,
текст 200% на 320/390/1440 px, клавиатурный выбор сессии, недоступность будущей
гонки, точная практика 2, возврат и сохранение фокуса, dialog и Escape,
ошибка и повтор результатов, пустой ответ и ответ с другим этапом. Основные
блоки не имеют горизонтального переполнения. Демонстрация изолирована от API;
`format=standard` задаёт три практики, `session=fp1|fp2|fp3|quali` открывает
сессию. `state=results-error|results-empty|results-mismatch` задаёт её исключения.

Контраст токенов сохранён: вторичный текст на фоне 5.26:1 / 8.56:1,
на поверхности 5.73:1 / 7.54:1, акцент на подсветке 5.39:1 / 7.11:1
(светлая / тёмная). Scoped Impeccable layout/type scan оставляет только три
предупреждения `overused-font` о сохранённом Space Grotesk.

Проверки: 193 фронтенд-теста, TypeScript, ESLint, `build:front`,
`git diff --check`. Реальный backend, календарное приложение, другие браузеры
и скринридер в этом проходе не проверялись. Отдельные времена Q1/Q2/Q3 по-прежнему требуют расширения API квалификации.


## Общий каркас и меню статистики — уточнение по референсам

«Уик-энд» теперь использует тот же HomeToolbar и glass-home каркас, что главная:
компактная тема, колокольчик с фактическим счётчиком и профиль в одной панели.
В мобильном виде штатный header заменяется общей панелью, на десктопе сохранён
sidebar и компактная панель справа. Юридический блок с уик-энда и его результатов
убран; документы остаются доступны в меню. Другие маршруты не переоформлялись.

Статистика открывается как нижний sheet на native dialog: вход 320 мс
с замедлением, выход 180 мс, прерывание по закрытию и Escape. При
prefers-reduced-motion пространственная анимация не запускается. Заголовок
и круглая кнопка закрытия остаются на месте, содержимое прокручивается отдельно;
фон блокируется, при закрытии восстанавливается прежний overflow и фокус.
Схема трассы, геометрия, секторы и слои не менялись.

Порядок информации под картой соответствует референсам: три состава шин,
две колонки оценок, исторические победы команды и пилота, открытие / первый GP,
рекорд круга / пилот, оценка потери на пит-стопе, раскрываемый блок «Шины».
В конце сохранены дополнительные факты и доступны источники данных.

Новый circuit-profile.ts содержит проверенный snapshot COTA 2026. Семь оценок,
C2/C3/C4, потеря 21,5 с и стартовые давления взяты из официальной инфографики
Pirelli от 20.10.2026. Прижимная сила не придумывается: в этом источнике такого
численного показателя нет. Победы относятся к COTA в 2012–2025, а не ко всем
трассам Гран-при США. История сверена с FIA / Formula 1 / Mercedes; рекорд и
год открытия — с Formula 1. URL источников находятся в данных и в меню.
Профиль не переносится на другой этап, архивный сезон или 2027 год.

Проверены обе темы, 320/390/699/700/899/900/1440/1920 px, текст 200% на
320/390/1440 px, единственный toolbar, отсутствие footer на уик-энде,
открытие/закрытие, Escape, начальный и возвращаемый фокус, прокрутка статистики
и отсутствие профиля 2026 в архиве 1997. Автоматические проверки: 195 тестов,
TypeScript, ESLint, build:front и diff check. Scoped layout/type detector отметил
только три использования сохранённого Space Grotesk. Реальный backend,
скринридер и системное переключение reduced motion отдельно не проверялись.

## Automatic circuit profiles and tyre illustrations — 25 October 2026

The Weekend sheet now requests `/api/circuit-profile?season=…&round=…`; the frontend no longer contains a COTA-only production snapshot. It checks the returned season, round and event name before displaying the profile. Failure has a retry action, unpublished/unsupported data stays absent, and retained data has its publication date and a stale label. Existing map geometry and the shared account toolbar remain unchanged.

The three slicks use original SVG tyre illustrations with depth, a sidewall and a wheel rim. Intermediate and Full Wet have distinct tread patterns and green/blue rings, available under the rain/pressure disclosure. Current tyre illustrations are hidden in archives before the 18-inch era (2022). The nominated C number belongs to that event; white/yellow/red indicate Hard/Medium/Soft roles. Meter fills use semantic scale tokens in both themes: 1–2 red, 3 yellow, 4–5 green. The number and accessible meter label remain the authoritative value; colour denotes intensity, not whether a property is desirable.

`app.services.pirelli_motorsport` discovers English articles from the official Formula 1 and season compound-selection archives. It binds allocation sentences to the named venue and previews to their exact season/event tags. OCR verifies the infographic heading/season/venue, locates labelled five-box scales and reads their unique red selection. At least seven scales must be validated. Starting pressures require agreement between two cropped OCR modes and a high-confidence number from the full image. Uncertain optional fields are omitted; a failed new infographic preserves the previous validated snapshot. The image hash is checked even when the article modification date is unchanged, allowing amended pressure graphics to be picked up. Unsupported formats are reported to worker operations, rather than silently assigned guessed values.

Circuit history comes from Jolpica's exact circuit ID. Wins include ties and exclude the selected race and later races; first F1 appearance and the quickest available race lap are computed from the same circuit history. Fastest-lap coverage is explicitly labelled from 2004 and includes previous configurations; it is not presented as a certified record for the current layout. Opening years are not inferred from first F1 appearances. History is warmed for every round, prioritising the nearest dates, with daily freshness for future rounds and weekly freshness for past rounds. Requests are spaced, and a 429 stops the batch and records Retry-After.

The existing worker owns the new `pirelli_motorsport` job: startup + every six hours. Web readers use the atomic JSON snapshot beside the configured database on the shared data volume. A separate process lock also protects manual CLI runs. Docker installs Tesseract and its English data. **Deployment requires rebuilding/restarting web and worker with this change**; no server deployment was performed by this design task. A diagnostic run is available with `python -m app.services.pirelli_motorsport --season 2026` in the configured application environment.

Live read-only checks extracted C2/C3/C4 for Austin and C3/C4/C5 for Mexico City and São Paulo from Pirelli. The Austin infographic yielded 7 validated scales, 21.5 s pit loss, 26.5/25.5 psi starting pressures; Singapore yielded its different 7 scales, including two red 2/5 values. Pressure recognition is deliberately conservative and is not guaranteed for every image layout. Some Pirelli articles returned 503 and the history provider returned 429 during the broader smoke run: retained data, partial-failure reporting and deferred retries cover these cases. No claim of a fully populated season or a running production job is made.

Verification: 195 frontend tests; scoped TypeScript/ESLint and production build; 41 backend tests across the new service and existing insights API. Scoped Impeccable layout/type scan reported only the three existing Space Grotesk warnings retained by the brand contract. Browser checks covered both themes, 320–1920 px and breakpoint boundaries, rain disclosure, all three meter colours on Singapore, retry recovery, Escape/focus restoration, empty profiles, archive isolation, and 200% text at 320/390/1440 px. A narrow rain grid stacks at large text; the descriptive copy explicitly overrides a legacy map paragraph colour to keep light-theme contrast.

The visual fixture uses the same response contract and recorded fact samples, with fictional calendar rounds clearly separated from production. `venue=singapore|mexico`, `state=profile-error|profile-unavailable|profile-stale` and `scale=2` cover these states without modifying accounts or backend data.
