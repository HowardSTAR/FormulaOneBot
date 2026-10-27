export const ONBOARDING_KEY = 'turbotears-onboarding-v2';
export const ONBOARDING_CHANGED = 'turbotears-onboarding-changed';
export const ONBOARDING_START = 'turbotears-onboarding-start';
export const startOnboarding = () => window.dispatchEvent(new Event(ONBOARDING_START));
export const onboardingSteps = [
  { route: '/', title: 'Главная', target: '.home-schedule', text: 'Здесь ближайшие сессии и время старта. Строка расписания открывает подробности этапа.' },
  { route: '/season', title: 'Календарь', target: '.calendar-filters', text: 'Переключайте предстоящие и прошедшие этапы. Нажмите на название гонки, чтобы открыть трассу и расписание.' },
  { route: '/race-results', title: 'Результаты', target: '.session-classification, .weekend-result-feedback, .weekend-empty, .weekend-result-loading', positions: '.session-result-position', text: 'В рамке — таблица результатов выбранной сессии. Выделенные номера слева — финишные позиции; справа — время, отставание и очки. Выше можно сменить сессию или открыть архив.' },
  { route: '/drivers', title: 'Пелотон', target: '.drivers-classification', positions: '.drivers-position', text: 'В рамке — личный зачёт. Выделенные места слева показывают позицию в чемпионате, справа — очки за сезон и последнюю гонку. Нажмите на строку пилота, чтобы открыть его карточку. Здесь же есть зачёт команд.' },
  { route: '/compare', title: 'Сравнение', target: '.comparison-controls', text: 'Выберите пилотов или команды для сравнения. Статистика и график появятся под этими настройками. История сезонов — в этом же разделе меню.' },
  { route: '/predictions', title: 'Прогнозы', target: '.predictions-tabs, .predictions-page header', text: 'Здесь прогноз на этап и его правила. После гонки — очки и личный разбор; для сохранения нужен аккаунт.' },
  { route: '/community', title: 'С друзьями', target: '.community-grid', text: 'Трасса недели, лиги прогнозов и общие результаты. Страницу можно прокручивать и изучать прямо сейчас.' },
  { route: '/wiki', title: 'Справочник F1', target: '.wiki-controls', text: 'Введите термин в поиск или выберите категорию. Ниже — правила, флаги и объяснения простыми словами.' },
  { route: '/reaction-game', title: 'Игры', target: '.reaction-board, .reaction-desktop-scene', text: 'Светофор помогает проверить реакцию. Другие игры — Reflex Grid и Emerald Loop — доступны в меню игр.' },
  { route: '/profile', title: 'Мой профиль', target: '.profile-hero, .profile-state', text: 'Профиль собирает ваш сезон: прогнозы, очки, рекорды и трофеи. «Аватар и оформление» меняет гонщика, рамку и цвет имени. Профилем можно поделиться с друзьями.', guestText: 'Войдите, чтобы открыть свой профиль: прогнозы и очки за сезон, рекорды, трофеи и избранных участников. Здесь можно настроить аватар и оформление, а затем поделиться профилем с друзьями.' },
  { route: '/profile', title: 'Ваш сезон в профиле', memberOnly: true, target: '.profile-season-block, .profile-state', text: 'Выбор сезона меняет сводку и список прогнозов. Раскройте этап, чтобы увидеть свои ответы и баллы; лучший результат отмечен отдельно. Рядом — личные рекорды на игровых трассах.' },
  { route: '/profile', title: 'Трофеи и избранное', memberOnly: true, target: '#profile-trophies, .profile-state', text: 'Здесь награды за прогнозы и игры. Откройте трофей, чтобы узнать условие, а полученную награду выберите бейджем у имени. Ниже — любимые пилоты и команды. Дополнительное оформление и клуб доступны по подписке Boosty.' },
  { route: '/account', title: 'Аккаунт и настройки', target: '.personal-hub-header, .account-grid, .account-hero', text: 'Здесь вход и привязка Telegram. Для проверки Boosty нужен одинаковый подтверждённый email на сайте и в Boosty. Часовой пояс и напоминания — в настройках.' },
  { route: '/account', title: 'Boosty и бонусы', target: '.account-boosty-card, .account-auth-card', text: 'На Boosty: «На старт» — значок и клуб; «Свой стиль» — рамки, цвет ника и фоны; «Полный газ» — вся коллекция. Проверка — в аккаунте, если доступна.' },
  { route: '/contact-admin', title: 'Обратная связь', target: '.contact-admin-form, .contact-admin-intro', text: 'Здесь можно сообщить об ошибке или предложить улучшение. Все основные разделы пройдены. Повторить знакомство можно в «Меню → Справка и аккаунт».', desktopText: 'Здесь можно сообщить об ошибке или предложить улучшение. Все основные разделы пройдены. Повторить знакомство можно в «Помощь → Короткое знакомство».' },
] as const;
type OnboardingState = { status: 'completed' | 'skipped' };
let sessionState: OnboardingState | null = null;

export function readOnboarding(): OnboardingState | null {
  try {
    const value = JSON.parse(localStorage.getItem(ONBOARDING_KEY) || 'null');
    if (value && ['completed', 'skipped'].includes(value.status)) return { status: value.status };
  } catch { /* Storage may be unavailable in an embedded or private browser. */ }
  return sessionState;
}

export function saveOnboarding(status: OnboardingState['status']) {
  sessionState = { status };
  try { localStorage.setItem(ONBOARDING_KEY, JSON.stringify(sessionState)); } catch { /* Keep the choice for this session. */ }
}
