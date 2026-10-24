import { Link } from 'react-router-dom';
import { useVisitReminder } from './useVisitReminder';
import './visit-reminder.css';

export function VisitReminder({ includeHome = false }: { includeHome?: boolean }) {
  const { reminder, close } = useVisitReminder({ includeHome });
  if (!reminder) return null;
  return <aside className={`visit-reminder${reminder.priority>=80 ? ' is-urgent' : ''}`} aria-label="Напоминание">
    <div className="visit-reminder-copy" role="status" aria-live="polite" aria-atomic="true">
      <strong>{reminder.title}</strong><span>{reminder.detail}</span>
    </div>
    <Link className="visit-reminder-action" to={reminder.to} onClick={close}>{reminder.action}</Link>
    <button type="button" className="visit-reminder-close" aria-label="Закрыть напоминание" onClick={close}>×</button>
  </aside>;
}
