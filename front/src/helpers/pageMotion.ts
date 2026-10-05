// The same order drives both the bottom indicator and horizontal page motion.
export function primaryNavigationIndex(pathname: string): number {
  if (pathname === '/') return 0;
  if (['/next-race', '/season', '/race-details', '/practice-results', '/race-results', '/quali-results', '/sprint-results', '/sprint-quali-results'].includes(pathname)) return 1;
  if (pathname === '/predictions') return 2;
  if (['/account', '/settings', '/favorites', '/notifications'].includes(pathname)) return 3;
  return 4;
}

export function pageMotionDirection(from: string, to: string): number {
  return Math.sign(primaryNavigationIndex(to) - primaryNavigationIndex(from));
}

export function preparePageMotion(from: string, to: string) {
  const direction = pageMotionDirection(from, to);
  document.documentElement.dataset.pageMotion = direction < 0 ? 'backward' : direction > 0 ? 'forward' : 'fade';
}
