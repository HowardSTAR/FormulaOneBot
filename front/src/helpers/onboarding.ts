export const ONBOARDING_KEY = 'turbotears-onboarding-v1';
export const ONBOARDING_CHANGED = 'turbotears-onboarding-changed';
export const onboardingGoals = [
  { id: 'schedule', title: 'Не пропускать сессии', description: 'Расписание уик-энда и календарь сезона', route: '/season', action: 'Открыть календарь', icon: '◷' },
  { id: 'predictions', title: 'Делать прогнозы', description: 'Мой прогноз, очки и место в рейтинге', route: '/predictions', action: 'Перейти к прогнозам', icon: '⚑' },
  { id: 'results', title: 'Разбираться в гонках', description: 'Результаты, сравнение пилотов и справочник', route: '/race-results', action: 'Посмотреть результаты', icon: '≋' },
] as const;
export type OnboardingGoal = typeof onboardingGoals[number]['id'];
type OnboardingState = { status: 'completed' | 'skipped'; goal: OnboardingGoal };
let sessionState: OnboardingState | null = null;

export function readOnboarding(): OnboardingState | null {
  try {
    const value = JSON.parse(localStorage.getItem(ONBOARDING_KEY) || 'null');
    if (value && ['completed', 'skipped'].includes(value.status) && onboardingGoals.some(goal => goal.id === value.goal)) return value;
  } catch { /* Storage may be unavailable in an embedded or private browser. */ }
  return sessionState;
}

export function saveOnboarding(status: OnboardingState['status'], goal: OnboardingGoal) {
  sessionState = { status, goal };
  try { localStorage.setItem(ONBOARDING_KEY, JSON.stringify(sessionState)); } catch { /* Keep the choice for this session. */ }
}
