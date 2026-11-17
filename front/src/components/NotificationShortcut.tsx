import { useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { apiRequest } from '../helpers/api';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { visibleInterval } from '../helpers/visibleInterval';
import { NOTIFICATIONS_CHANGED_EVENT } from '../helpers/notificationPresentation';
import { HomeIcon } from '../pages/index/HomeIcon';
import { useVisitReminder } from './useVisitReminder';
import { VisitReminder } from './VisitReminder';
import './notification-shortcut.css';

export function NotificationShortcut({ showReminder }: { showReminder: boolean }) {
  const auth = useAuthState();
  const { pathname, key } = useLocation();
  const { reminder, close } = useVisitReminder({ enabled: showReminder, includeHome: pathname === '/' || pathname === '/menu' });
  const panelId = useId();
  const restoreInboxFocus = useRef(false);
  const [unread, setUnread] = useState<number | null>(null);
  useEffect(() => { const clear = () => setUnread(null); window.addEventListener(AUTH_CHANGED_EVENT, clear); return () => window.removeEventListener(AUTH_CHANGED_EVENT, clear); }, []);
  useEffect(() => {
    if (!auth.loaded || !auth.signedIn) return;
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
  }, [auth.loaded, auth.signedIn, pathname]);

  const count = auth.signedIn ? unread : null;
  const label = count === null ? 'Уведомления: количество неизвестно' : `Уведомления: непрочитанных ${count}`;
  const bell = <>
    <HomeIcon name="notifications" />
    {count !== null && count > 0 ? <span aria-hidden="true">{count > 99 ? '99+' : count}</span>
      : reminder && <span className="notification-reminder-dot" aria-hidden="true" />}
  </>;
  const current = pathname === '/notifications' ? 'page' : undefined;

  if (reminder) {
    const reminderLabel = auth.signedIn ? `${label}. Есть напоминание` : 'Есть напоминание';
    return <>
      <button type="button" className="notification-shortcut" aria-label={reminderLabel} title={reminderLabel}
        aria-current={current} popoverTarget={panelId}>
        {bell}
      </button>
      <VisitReminder key={`${key}:${reminder.id}`} id={panelId} reminder={reminder} signedIn={auth.signedIn}
        onAction={close} onDismiss={event => {
          restoreInboxFocus.current = auth.signedIn;
          if (!auth.signedIn) event.currentTarget.closest('.home-toolbar')?.querySelector<HTMLButtonElement>('.theme-toggle')?.focus();
          close();
        }} />
    </>;
  }

  return auth.signedIn ? <Link className="notification-shortcut" to="/notifications" aria-label={label} title={label}
    aria-current={current} ref={node => {
      if (!node || !restoreInboxFocus.current) return;
      restoreInboxFocus.current = false;
      node.focus();
    }}>
    {bell}
  </Link> : null;
}
