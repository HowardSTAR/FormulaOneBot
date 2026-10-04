import { apiRequest } from './api';
import { hasTelegramAuth } from './auth';
import { pageTitles } from './pageTitles';

export function analyticsPlatform() {
  if (hasTelegramAuth()) return 'telegram';
  if (window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone) return 'pwa';
  return 'browser';
}

export function trackPrediction(event: 'prediction_view' | 'prediction_start', season: number, round: number) {
  queue = queue.then(() => apiRequest('/api/analytics/event', { event, path: '/predictions', season, round, platform: analyticsPlatform() }, 'POST', 5000)).then(() => {}).catch(() => {});
}

const actions = new Set(['calendar_open','session_open','results_open','compare_open','history_open','wiki_open',
  'prediction_submit','game_start','game_restart','settings_save','favorites_toggle','vote_submit','review_open',
  'filter_change','tab_change','back','expand','button','navigate','screen','game_hit']);
let queue = Promise.resolve();
const recent = new Map<string, number>();
export function analyticsPath(path: string): string | null {
  if (path.startsWith('/share/')) return '/share';
  return pageTitles[path] && !['/admin','/prediction-analytics','/reset-password'].includes(path) ? path : null;
}
export function trackAction(action: string, path = window.location.pathname, destination = '') {
  const safePath = analyticsPath(path);
  if (!safePath || !actions.has(action)) return;
  const key = `${safePath}:${action}:${destination}`;
  const now = Date.now();
  if (now - (recent.get(key) || 0) < 700) return;
  recent.set(key, now);
  if (recent.size > 100) recent.delete(recent.keys().next().value!);
  const body = {event: 'click', action, path: safePath, destination: analyticsPath(destination) || '',
    event_id: crypto.randomUUID(), platform: analyticsPlatform()};
  queue = queue.then(() => apiRequest('/api/analytics/event', body, 'POST', 5000)).then(() => {}).catch(() => {});
}
export function trackScreen(path: string) {
  const safePath = analyticsPath(path);
  if (!safePath) return;
  queue = queue.then(async () => {
    await apiRequest('/api/analytics/visit', {path: safePath, platform: analyticsPlatform()}, 'POST', 5000);
    await apiRequest('/api/analytics/event', {event: 'screen_view', action: 'screen', path: safePath,
      event_id: crypto.randomUUID(), platform: analyticsPlatform()}, 'POST', 5000);
  }).catch(() => {});
}

/** Only stable action codes and public route names. Never collect text, values or query strings. */
export function observeActions() {
  const click = (event: MouseEvent) => {
    const target = event.target instanceof Element ? event.target.closest('button,a,summary,[data-analytics-action]') : null;
    if (!target || target.matches(':disabled,[aria-disabled="true"]')) return;
    let destination = '';
    if (target instanceof HTMLAnchorElement) {
      const url = new URL(target.href, window.location.origin);
      if (url.origin === window.location.origin) destination = analyticsPath(url.pathname) || '';
    }
    const action = target.getAttribute('data-analytics-action') || (target.tagName === 'SUMMARY' ? 'expand'
      : destination ? 'navigate' : target.closest('.segmented-tabs,.predictions-tabs,.voting-tabs') ? 'tab_change' : 'button');
    trackAction(action, window.location.pathname, destination);
  };
  const change = (event: Event) => {
    if (event.target instanceof HTMLSelectElement) trackAction('filter_change');
  };
  document.addEventListener('click', click, {capture: true});
  document.addEventListener('change', change, {capture: true});
  return () => { document.removeEventListener('click', click, {capture: true}); document.removeEventListener('change', change, {capture: true}); };
}
