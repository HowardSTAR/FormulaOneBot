import { apiRequest } from './api';

const entries = new Map<string, {eventId:string; request?:Promise<boolean>}>();

/** One event per destination opening, including React StrictMode effect replays. */
export function trackNotificationEntry(token: string, path: string, openingId: string): Promise<boolean> {
  if (!/^[A-Za-z0-9_-]{32}$/.test(token) || !['/predictions', '/community'].includes(path)) return Promise.resolve(false);
  const key = `${openingId}:${path}:${token}`;
  const entry = entries.get(key) || {eventId:crypto.randomUUID()};
  if (entry.request) return entry.request;
  const request = apiRequest('/api/analytics/notification-entry', {
    token, path, event_id:entry.eventId,
  }, 'POST', 5000).then(() => true).catch(() => {entry.request = undefined; return false;});
  entry.request = request;
  entries.set(key, entry);
  return request;
}
