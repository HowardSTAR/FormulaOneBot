import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { apiRequest } from '../helpers/api';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { visibleInterval } from '../helpers/visibleInterval';
import { useVisibleClock } from '../helpers/useVisibleClock';
import { useHeroData } from '../context/useHeroData';
import { dismissReminder, reminderAllowed, visitReminders, type VisitData } from '../helpers/visitReminders';
import './visit-reminder.css';

export function VisitReminder() {
  const auth = useAuthState();
  const {pathname} = useLocation();
  const {load,loaded,nextRace,schedule} = useHeroData();
  const [data,setData] = useState<VisitData | null>(null);
  const [closed,setClosed] = useState(false);
  const now = useVisibleClock(30000,auth.loaded);
  useEffect(()=>{if (!loaded) void load()},[loaded,load]);
  useEffect(()=>{
    if (!auth.loaded) return;
    let active = true, generation = 0;
    const refresh = async () => {
      const request = ++generation;
      const [personal,prediction,week] = await Promise.allSettled([
        auth.signedIn ? apiRequest<Pick<VisitData,'user_id'|'weekly'>>('/api/engagement/weekly/me') : Promise.resolve({user_id:null,weekly:null}),
        apiRequest<NonNullable<VisitData['prediction']>>(auth.signedIn ? '/api/predictions/current' : '/api/predictions/preview'),
        apiRequest<NonNullable<VisitData['week']>>('/api/engagement/weekly'),
      ]);
      if (!active || request!==generation) return;
      // Do not turn a failed personal lookup into "you haven't raced".
      if (personal.status==='rejected') {setData(null);return}
      setData({...personal.value,prediction:prediction.status==='fulfilled' ? prediction.value : null,
        week:week.status==='fulfilled' ? week.value : null});
    };
    const identityChanged = () => {generation++;setData(null);setClosed(false);void refresh()};
    void refresh();
    const stop = visibleInterval(()=>void refresh(),60000);
    window.addEventListener(AUTH_CHANGED_EVENT,identityChanged);
    return ()=>{active=false;generation++;stop();window.removeEventListener(AUTH_CHANGED_EVENT,identityChanged)};
  },[auth.loaded,auth.signedIn]);
  const excluded = ['/admin','/prediction-analytics','/reset-password','/contact-admin','/account/delete','/race-game','/reaction-game','/reflex-grid-game','/account'];
  if (!data || closed || !auth.loaded || excluded.includes(pathname)) return null;
  if (auth.signedIn && data.user_id===null || !auth.signedIn && data.user_id!==null) return null;
  const sessions = nextRace?.is_cancelled ? [] : schedule.length ? schedule : nextRace?.next_session_iso
    ? [{name:nextRace.next_session_name || 'Сессия',utc_iso:nextRace.next_session_iso}] : [];
  const reminder = visitReminders(data,sessions,now,nextRace?.event_name)
    .find(item=>item.to.split('?')[0]!==pathname && reminderAllowed(item,data.user_id,now));
  if (!reminder) return null;
  const close = () => {dismissReminder(reminder,data.user_id,Date.now());setClosed(true)};
  return <aside className={`visit-reminder${reminder.priority>=80 ? ' is-urgent' : ''}`} aria-label="Напоминание">
    <div className="visit-reminder-copy" role="status" aria-live="polite" aria-atomic="true">
      <strong>{reminder.title}</strong><span>{reminder.detail}</span>
    </div>
    <Link className="visit-reminder-action" to={reminder.to} onClick={close}>{reminder.action}</Link>
    <button type="button" className="visit-reminder-close" aria-label="Закрыть напоминание" onClick={close}>×</button>
  </aside>;
}
