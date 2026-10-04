export const ONBOARDING_KEY = 'turbotears-onboarding-v2';
export const ONBOARDING_CHANGED = 'turbotears-onboarding-changed';
export const onboardingSteps = [
  { route: '/', title: 'Главная', target: '#hero-sub', text: 'Ближайшая сессия, отсчёт до старта и расписание уик-энда. Отсюда удобно начинать перед каждой гонкой.' },
  { route: '/season', title: 'Календарь', text: 'Все этапы сезона и время сессий. Выберите этап, чтобы посмотреть расписание, трассу и доступные результаты.' },
  { route: '/race-results', title: 'Результаты', text: 'Итоги гонок, квалификаций, спринтов и практик. Переключайте сезон и этап, чтобы открыть нужную сессию.' },
  { route: '/drivers', title: 'Пелотон', text: 'Зачёт пилотов и команд, очки и карточки участников. Нажмите на пилота или команду, чтобы узнать подробности.' },
  { route: '/compare', title: 'Аналитика', text: 'Сравнивайте пилотов и команды. В истории сезонов можно проследить, как менялся чемпионат.' },
  { route: '/predictions', title: 'Прогнозы', text: 'Выберите исходы следующего этапа до указанного срока. После гонки появятся очки и личный разбор; для сохранения нужен аккаунт.' },
  { route: '/community', title: 'С друзьями', text: 'Соревнуйтесь на трассе недели, создавайте лиги прогнозов и делитесь карточками результатов.' },
  { route: '/wiki', title: 'Справочник F1', text: 'Правила, флаги и гоночные термины простыми словами. Введите незнакомый термин в поиск.' },
  { route: '/reaction-game', title: 'Игры', text: 'Проверьте реакцию на светофоре. В меню игр также есть Reflex Grid и пиксельная гонка Emerald Loop.' },
  { route: '/account', title: 'Аккаунт и настройки', text: 'После входа доступны личные результаты и настройки часового пояса и напоминаний. Привяжите Telegram для избранного и голосования.' },
  { route: '/contact-admin', title: 'Обратная связь', text: 'Нашли ошибку или хотите предложить улучшение? Здесь можно написать администратору. Знакомство завершено — возвращаемся на главную.' },
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
