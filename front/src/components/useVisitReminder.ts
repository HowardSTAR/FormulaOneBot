import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { apiRequest } from '../helpers/api';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { visibleInterval } from '../helpers/visibleInterval';
import { useVisibleClock } from '../helpers/useVisibleClock';
import { useHeroData } from '../context/useHeroData';
import { dismissReminder, reminderAllowed, visitReminders, type VisitData } from '../helpers/visitReminders';

export function useVisitReminder({ enabled = true, includeHome = false } = {}) {
  const auth = useAuthState();
  const { pathname } = useLocation();
  const { load, loaded, nextRace, schedule } = useHeroData();
  const [data, setData] = useState<VisitData | null>(null);
  const [closed, setClosed] = useState(false);
  const now = useVisibleClock(30000, enabled && auth.loaded);
  useEffect(() => { if (enabled && !loaded) void load(); }, [enabled, loaded, load]);
  useEffect(() => {
    if (!enabled || !auth.loaded) return;
    let active = true, generation = 0;
    const refresh = async () => {
      const request = ++generation;
      const [personal, prediction, week] = await Promise.allSettled([
        auth.signedIn ? apiRequest<Pick<VisitData, 'user_id' | 'weekly'>>('/api/engagement/weekly/me') : Promise.resolve({ user_id: null, weekly: null }),
        apiRequest<NonNullable<VisitData['prediction']>>(auth.signedIn ? '/api/predictions/current' : '/api/predictions/preview'),
        apiRequest<NonNullable<VisitData['week']>>('/api/engagement/weekly'),
      ]);
      if (!active || request !== generation) return;
      if (personal.status === 'rejected') { setData(null); return; }
      setData({ ...personal.value, prediction: prediction.status === 'fulfilled' ? prediction.value : null, week: week.status === 'fulfilled' ? week.value : null });
    };
    const identityChanged = () => { generation++; setData(null); setClosed(false); void refresh(); };
    void refresh();
    const stop = visibleInterval(() => void refresh(), 60000);
    window.addEventListener(AUTH_CHANGED_EVENT, identityChanged);
    return () => { active = false; generation++; stop(); window.removeEventListener(AUTH_CHANGED_EVENT, identityChanged); };
  }, [enabled, auth.loaded, auth.signedIn]);
  const sessions = nextRace?.is_cancelled ? [] : schedule.length ? schedule : nextRace?.next_session_iso
    ? [{ name: nextRace.next_session_name || 'Сессия', utc_iso: nextRace.next_session_iso }] : [];
  const excluded = ['/admin', '/prediction-analytics', '/reset-password', '/contact-admin', '/account/delete', '/race-game', '/reaction-game', '/reflex-grid-game', '/account'];
  const allowed = enabled && data && !closed && auth.loaded && !excluded.includes(pathname)
    && (auth.signedIn ? data.user_id !== null : data.user_id === null);
  const reminder = allowed ? visitReminders(data, sessions, now, nextRace?.event_name).find(item =>
    item.to.split('?')[0] !== pathname && (includeHome || pathname !== '/' || !/^(session:|(?:new|missing)-prediction:)/.test(item.id)) && reminderAllowed(item, data.user_id, now)) : undefined;
  const close = () => { if (reminder && data) dismissReminder(reminder, data.user_id, Date.now()); setClosed(true); };
  return { reminder, close };
}
