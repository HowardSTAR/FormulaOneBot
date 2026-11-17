import type { MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import type { VisitReminder as Reminder } from '../helpers/visitReminders';
import { HomeIcon } from '../pages/index/HomeIcon';
import './visit-reminder.css';

type Props = {
  id: string;
  reminder: Reminder;
  signedIn: boolean;
  onAction: () => void;
  onDismiss: (event: MouseEvent<HTMLButtonElement>) => void;
};

export function VisitReminder({ id, reminder, signedIn, onAction, onDismiss }: Props) {
  return <aside id={id} className="visit-reminder" aria-label="Напоминание" popover="auto"
    onBeforeToggle={event => {
      if (event.newState !== 'open' || CSS.supports('inset-block-start: anchor(bottom)')) return;
      const panel = event.currentTarget;
      const toolbar = panel.closest('.home-toolbar')?.getBoundingClientRect();
      if (!toolbar) return;
      panel.style.setProperty('--reminder-top', `${toolbar.bottom + 8}px`);
      panel.style.setProperty('--reminder-right', `${document.documentElement.clientWidth - toolbar.right}px`);
    }}>
    <div className="visit-reminder-body">
      <div className="visit-reminder-copy">
        <strong>{reminder.title}</strong>
        {reminder.detail && <p>{reminder.detail}</p>}
      </div>
      <Link className="visit-reminder-action" to={reminder.to} onClick={event => {
        if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) onAction();
      }}>{reminder.action}</Link>
      <button type="button" className="visit-reminder-dismiss" aria-label="Скрыть напоминание"
        title="Скрыть напоминание" onClick={onDismiss}>
        <HomeIcon name="close" />
      </button>
    </div>
    {signedIn && <Link className="visit-reminder-inbox" to="/notifications">Все уведомления</Link>}
  </aside>;
}
