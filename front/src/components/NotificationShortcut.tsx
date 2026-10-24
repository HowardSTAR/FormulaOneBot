import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { apiRequest } from '../helpers/api';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { visibleInterval } from '../helpers/visibleInterval';
import { NOTIFICATIONS_CHANGED_EVENT } from '../helpers/notificationPresentation';
import { HomeIcon } from '../pages/index/HomeIcon';
import './notification-shortcut.css';

export function NotificationShortcut({ enabled = true }: { enabled?: boolean }) {
  const auth = useAuthState();
  const { pathname } = useLocation();
  const [unread, setUnread] = useState<number | null>(null);
  useEffect(() => { const clear = () => setUnread(null); window.addEventListener(AUTH_CHANGED_EVENT, clear); return () => window.removeEventListener(AUTH_CHANGED_EVENT, clear); }, []);
  useEffect(() => {
    if (!enabled || !auth.loaded || !auth.signedIn) return;
    let active = true, generation = 0;
    const refresh = async () => {
      const request = ++generation;
      try { const data = await apiRequest<{ unread: number }>('/api/web-notifications/unread-count'); if (active && request === generation) setUnread(Number.isInteger(data.unread) && data.unread >= 0 ? data.unread : null); }
      catch { if (active && request === generation) setUnread(null); }
    };
    const reset = () => { generation++; setUnread(null); void refresh(); };
    void refresh();
    const stop = visibleInterval(() => void refresh(), 60000);
    window.addEventListener('focus', refresh);
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, refresh);
    window.addEventListener(AUTH_CHANGED_EVENT, reset);
    return () => { active = false; generation++; stop(); window.removeEventListener('focus', refresh); window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, refresh); window.removeEventListener(AUTH_CHANGED_EVENT, reset); };
  }, [enabled, auth.loaded, auth.signedIn, pathname]);
  if (!enabled || !auth.signedIn) return null;
  const label = unread === null ? 'Уведомления: количество неизвестно' : `Уведомления: непрочитанных ${unread}`;
  return <Link className="notification-shortcut" to="/notifications" aria-label={label} title={label} aria-current={pathname === '/notifications' ? 'page' : undefined}><HomeIcon name="notifications" />{unread !== null && unread > 0 && <span aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}</Link>;
}
