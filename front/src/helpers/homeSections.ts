// One set of home destinations for the mobile switcher and desktop sidebar.
export const homeSections = [
  { id: 'season', label: 'Сезон', icon: 'home' },
  { id: 'games', label: 'Игры', icon: 'games' },
  { id: 'guide', label: 'Справка и отзывы', icon: 'wiki' },
  { id: 'subscription', label: 'Подписка', icon: 'favorite' },
] as const;
export type HomeSection = typeof homeSections[number]['id'];
export function homeSectionFromSearch(search: string | URLSearchParams): HomeSection {
  const requested = new URLSearchParams(search).get('view');
  const value = requested === 'wiki' || requested === 'reviews' ? 'guide' : requested;
  return homeSections.find(section => section.id === value)?.id || 'season';
}
export function homeSectionPath(section: HomeSection, search: string | URLSearchParams = ''): string {
  const next = new URLSearchParams(search);
  if (section === 'season') next.delete('view'); else next.set('view', section);
  return `/${next.size ? `?${next}` : ''}`;
}
