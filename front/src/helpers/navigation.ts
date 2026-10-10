import type { AuthState } from './auth';
import type { IndexIconName } from '../pages/index/IndexIcon';

export type NavigationItem = { to: string; label: string; icon: IndexIconName; activePaths: string[]; access?: 'signedIn' | 'personalized' | 'admin' };
export type NavigationGroup = { id: string; label: string; icon: IndexIconName; items: NavigationItem[] };
const item = (to: string, label: string, icon: IndexIconName, activePaths = [to], access?: NavigationItem['access']): NavigationItem => ({ to, label, icon, activePaths, access });
const primary = [item('/', 'Обзор', 'home'), item('/season', 'Календарь', 'calendar', ['/season', '/next-race', '/race-details'])];
const general = [item('/community', 'С друзьями', 'games'), item('/wiki', 'Wiki Formula 1™', 'wiki'), item('/profile', 'Моё', 'account', ['/profile', '/account', '/favorites', '/settings']), item('/notifications', 'Уведомления', 'notifications', undefined, 'personalized'), item('/contact-admin', 'Обратная связь', 'contact')];
const personal = [item('/admin', 'Админ-панель', 'admin', undefined, 'admin'), item('/voting', 'Голосование', 'vote', undefined, 'personalized')];
const groups: NavigationGroup[] = [
  { id: 'results', label: 'Результаты', icon: 'results', items: [
    item('/practice-results', 'Свободные заезды', 'practice'), item('/sprint-quali-results', 'Спринт-квалификация', 'sprintQuali'), item('/sprint-results', 'Спринт-гонка', 'sprint'), item('/quali-results', 'Квалификация', 'quali'), item('/race-results', 'Гонка', 'race'),
  ] },
  { id: 'peloton', label: 'Пелотон', icon: 'peloton', items: [
    item('/drivers', 'Пилоты', 'drivers', ['/drivers', '/driver-details']), item('/constructors', 'Команды', 'teams', ['/constructors', '/constructor-details', '/team-principal']), item('/history', 'История сезонов', 'compare'),
  ] },
  { id: 'analytics', label: 'Аналитика', icon: 'analytics', items: [item('/compare', 'Сравнение', 'compare'), item('/predictions', 'Прогнозы', 'predictions'), item('/prediction-analytics', 'Аналитика предсказаний', 'predictionAnalytics', undefined, 'admin')] },
  { id: 'games', label: 'Игры', icon: 'games', items: [item('/reaction-game', 'Тест реакции', 'reaction'), item('/reflex-grid-game', 'Reflex Grid', 'grid'), item('/race-game', 'Emerald Loop', 'arcade')] },
];

export function navigationFor(auth: Pick<AuthState, 'signedIn' | 'personalized' | 'role'>) {
  const allowed = (link: NavigationItem) => !link.access || (link.access === 'admin' ? auth.role === 'admin' || auth.role === 'superadmin' : auth[link.access]);
  return { primary, general: general.filter(allowed), personal: personal.filter(allowed), groups: groups.map(group => ({ ...group, items: group.items.filter(allowed) })) };
}
export const navigationActive = (item: NavigationItem, pathname: string) => item.activePaths.some(path => pathname === path || path !== '/' && pathname.startsWith(`${path}/`));
