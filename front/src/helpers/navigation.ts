import type { AuthState } from './auth';
import type { IndexIconName } from '../pages/index/IndexIcon';

export type NavigationItem = { to: string; label: string; icon: IndexIconName; activePaths: string[]; access?: 'signedIn' | 'personalized' | 'admin' };
export type NavigationAction = { id: 'onboarding'; label: string; icon: IndexIconName };
export type NavigationGroup = { id: string; label: string; icon: IndexIconName; items: NavigationItem[]; actions?: NavigationAction[] };
export type NavigationSection = { id: string; label: string; items: (NavigationItem | NavigationGroup)[] };
const item = (to: string, label: string, icon: IndexIconName, activePaths = [to], access?: NavigationItem['access']): NavigationItem => ({ to, label, icon, activePaths, access });
const home = item('/', 'Обзор', 'home');
const weekend = item('/next-race', 'Уик-энд', 'race');
const calendar = item('/season', 'Календарь', 'calendar', ['/season', '/race-details']);
const predictions = item('/predictions', 'Прогнозы', 'predictions');
const community = item('/community', 'С друзьями', 'social');
const wiki = item('/wiki', 'Wiki Formula 1™', 'wiki');
const profile = item('/profile', 'Мой профиль', 'account', ['/profile', '/account', '/favorites', '/settings']);
const notifications = item('/notifications', 'Уведомления', 'notifications', undefined, 'personalized');
const feedback = item('/contact-admin', 'Обратная связь', 'contact');
const admin = item('/admin', 'Админ-панель', 'admin', undefined, 'admin');
const predictionAnalytics = item('/prediction-analytics', 'Аналитика предсказаний', 'predictionAnalytics', undefined, 'admin');
const voting = item('/voting', 'Голосование', 'vote', undefined, 'personalized');
const primary = [home, weekend, calendar, predictions];
const general = [community, wiki, profile, notifications, feedback];
const personal = [admin, predictionAnalytics, voting];
const groups: NavigationGroup[] = [
  { id: 'results', label: 'Результаты', icon: 'results', items: [
    item('/practice-results', 'Свободные заезды', 'practice'), item('/sprint-quali-results', 'Спринт-квалификация', 'sprintQuali'), item('/sprint-results', 'Спринт-гонка', 'sprint'), item('/quali-results', 'Квалификация', 'quali'), item('/race-results', 'Гонка', 'race'),
  ] },
  { id: 'peloton', label: 'Пелотон', icon: 'peloton', items: [
    item('/drivers', 'Пилоты', 'drivers', ['/drivers', '/driver-details']), item('/constructors', 'Команды', 'teams', ['/constructors', '/constructor-details', '/team-principal']),
  ] },
  { id: 'comparison', label: 'Сравнение', icon: 'compare', items: [item('/compare', 'Сравнение пилотов', 'compare'), item('/history', 'История сезонов', 'compare')] },
  { id: 'games', label: 'Игры', icon: 'games', items: [item('/reaction-game', 'Тест реакции', 'reaction'), item('/reflex-grid-game', 'Reflex Grid', 'grid'), item('/race-game', 'Emerald Loop', 'arcade')] },
];
const [results, peloton, comparison, games] = groups;
const desktopSections: NavigationSection[] = [
  { id: 'racing', label: 'Гонки', items: [home, weekend, calendar, results, peloton] },
  { id: 'statistics', label: 'Прогнозы и статистика', items: [predictions, comparison] },
  { id: 'community', label: 'Сообщество', items: [
    { id: 'social', label: 'С друзьями', icon: 'social', items: [{ ...community, label: 'Сообщество' }, voting] }, games,
  ] },
  { id: 'personal', label: 'Личное и справка', items: [
    { id: 'personal', label: 'Мой профиль', icon: 'account', items: [
      item('/profile', 'Профиль', 'account', undefined, 'signedIn'), item('/account', 'Аккаунт', 'account'),
      item('/favorites', 'Избранное', 'favorite', undefined, 'personalized'), notifications,
      item('/settings', 'Настройки', 'settings', undefined, 'signedIn'),
    ] }, wiki,
    { id: 'help', label: 'Помощь', icon: 'help', items: [feedback], actions: [{ id: 'onboarding', label: 'Короткое знакомство', icon: 'wiki' }] },
  ] },
];
const management: NavigationGroup = { id: 'management', label: 'Управление', icon: 'admin', items: [admin, predictionAnalytics] };

// Section entry points never need an in-page back button. Detail routes still do.
const sectionRoots = new Set([
  '/', '/next-race', '/account', '/settings', '/favorites',
  ...[...primary, ...general, ...personal, ...groups.flatMap(group => group.items)].map(link => link.to),
]);
export const isSectionRoot = (pathname: string) => sectionRoots.has(pathname.replace(/\/+$/, '') || '/');

export function navigationFor(auth: Pick<AuthState, 'signedIn' | 'personalized' | 'role'>) {
  const allowed = (link: NavigationItem) => !link.access || (link.access === 'admin' ? auth.role === 'admin' || auth.role === 'superadmin' : auth[link.access]);
  const filterGroup = (group: NavigationGroup): NavigationGroup => ({ ...group, items: group.items.filter(allowed) });
  const filteredManagement = filterGroup(management);
  return {
    primary, general: general.filter(allowed), personal: personal.filter(allowed), groups: groups.map(filterGroup),
    sections: desktopSections.map(section => ({ ...section, items: section.items.flatMap<NavigationItem | NavigationGroup>(entry => {
      if ('to' in entry) return allowed(entry) ? [entry] : [];
      const group = filterGroup(entry);
      return group.items.length || group.actions?.length ? [group] : [];
    }) })),
    management: filteredManagement.items.length ? filteredManagement : null,
  };
}
export const navigationActive = (item: NavigationItem, pathname: string) => item.activePaths.some(path => pathname === path || path !== '/' && pathname.startsWith(`${path}/`));
