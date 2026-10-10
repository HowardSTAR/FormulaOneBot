export const ONBOARDING_KEY = 'turbotears-onboarding-v2';
export const ONBOARDING_CHANGED = 'turbotears-onboarding-changed';
export const ONBOARDING_START = 'turbotears-onboarding-start';
export const startOnboarding = () => window.dispatchEvent(new Event(ONBOARDING_START));
export const onboardingSteps = [
  { route: '/', title: 'Главная', target: '.weekend-board', text: 'Здесь ближайшие сессии и время старта. Строка расписания открывает подробности этапа.' },
  { route: '/season', title: 'Календарь', target: '.season-filters', text: 'Переключайте предстоящие и прошедшие этапы. Нажмите на название гонки, чтобы открыть трассу и расписание.' },
  { route: '/race-results', title: 'Результаты', target: '.race-results-desktop-controls, .race-results-mobile .segmented-tabs, .segmented-tabs', text: 'Последняя гонка — в первой вкладке. В архиве можно выбрать сезон и этап; ниже показана классификация.' },
  { route: '/drivers', title: 'Пелотон', target: '.drivers-standings-table, .standings-cards-grid', text: 'Места и очки пилотов. Откройте карточку участника; зачёт команд доступен в меню пелотона.' },
  { route: '/compare', title: 'Сравнение', target: '.compare-controls-panel', text: 'Выберите пилотов или команды для сравнения. Статистика и график появятся под этими настройками. История сезонов — в этом же разделе меню.' },
  { route: '/predictions', title: 'Прогнозы', target: '.predictions-tabs', text: 'Здесь прогноз на этап и его правила. После гонки — очки и личный разбор; для сохранения нужен аккаунт.' },
  { route: '/community', title: 'С друзьями', target: '.community-grid', text: 'Трасса недели, лиги прогнозов и общие результаты. Страницу можно прокручивать и изучать прямо сейчас.' },
  { route: '/wiki', title: 'Справочник F1', target: '.wiki-controls', text: 'Введите термин в поиск или выберите категорию. Ниже — правила, флаги и объяснения простыми словами.' },
  { route: '/reaction-game', title: 'Игры', target: '.reaction-board, .reaction-desktop-scene', text: 'Светофор помогает проверить реакцию. Другие игры — Reflex Grid и Emerald Loop — доступны в меню игр.' },
  { route: '/account', title: 'Аккаунт и настройки', target: '.account-tabs, .account-grid, .account-hero', text: 'Вход, личные результаты и привязка Telegram. Часовой пояс и напоминания меняются в настройках.' },
  { route: '/contact-admin', title: 'Обратная связь', target: '.contact-admin-form, .contact-admin-page header', text: 'Здесь можно сообщить об ошибке или предложить улучшение. Все основные разделы пройдены. Повторить знакомство можно в «Меню → Справка и аккаунт».', desktopText: 'Здесь можно сообщить об ошибке или предложить улучшение. Все основные разделы пройдены. Повторить знакомство можно в «Помощь → Короткое знакомство».' },
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
