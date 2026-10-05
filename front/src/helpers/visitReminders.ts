import type { PersonalPrediction } from '../pages/index/personal-summary';

export type VisitReminder = {id: string; title: string; detail: string; action: string; to: string; priority: number; expires: number};
export type WeeklyReminder = {week: string; end: string; track_id: string; name: string; time_ms: number; place: number; alert_id: number | null; rival: {name: string; time_ms: number} | null};
export type VisitData = {user_id: number | null; weekly: WeeklyReminder | null; prediction: PersonalPrediction | null;
  week: {track_id: string; name: string; start: string; end: string} | null};
type Session = {name: string; utc_iso?: string};
const formatTime = (ms: number) => `${Math.floor(ms/60000)}:${(ms/1000%60).toFixed(3).padStart(6,'0')}`;

export function visitReminders(data: VisitData, sessions: Session[], now: number, raceName = ''): VisitReminder[] {
  const reminders: VisitReminder[] = [];
  const weekly = data.weekly;
  if (weekly?.rival && weekly.alert_id && Date.parse(weekly.end)>now) {
    reminders.push({id:`overtaken:${weekly.week}:${weekly.alert_id}`,title:'Твоё время обошли',
      detail:`${weekly.rival.name} — ${formatTime(weekly.rival.time_ms)}`,
      action:'Перебить время →',to:`/race-game?track=${encodeURIComponent(weekly.track_id)}&weekly=1`,priority:100,expires:Date.parse(weekly.end)});
  }
  const next = sessions.filter(session=>session.utc_iso && /(Z|[+-]\d\d:\d\d)$/i.test(session.utc_iso))
    .map(session=>({...session,start:Date.parse(session.utc_iso!)})).filter(session=>session.start>now && session.start-now<=86400000)
    .sort((a,b)=>a.start-b.start)[0];
  if (next) {
    const minutes = Math.ceil((next.start-now)/60000);
    const countdown = minutes<60 ? `${minutes} мин` : `${Math.floor(minutes/60)} ч${minutes%60 ? ` ${minutes%60} мин` : ''}`;
    reminders.push({id:`session:${next.utc_iso}:${next.name}`,title:`${next.name} через ${countdown}`,
      detail:raceName,action:'Расписание →',to:'/next-race',priority:minutes<=120 ? 90 : 40,expires:next.start});
  }
  const prediction = data.prediction;
  const deadline = Date.parse(prediction?.deadline_utc || '');
  const opens = Date.parse(prediction?.opens_at_utc || '');
  if (prediction?.status==='ok' && prediction.is_open && !prediction.prediction
    && deadline>now && (!Number.isFinite(opens) || opens<=now)) {
    const urgent = deadline-now<=86400000;
    reminders.push({id:`${urgent ? 'missing' : 'new'}-prediction:${prediction.season}:${prediction.round}`,
      title:urgent ? 'Не забудь сохранить прогноз' : 'Доступен новый прогноз',
      detail:`${prediction.event_name || 'Ближайший этап'}${urgent ? ` · осталось ${Math.max(1,Math.ceil((deadline-now)/3600000))} ч` : ''}`,
      action:'Сделать прогноз →',to:'/predictions',priority:urgent ? 80 : 60,expires:deadline});
  }
  const week = data.week;
  if (week && !weekly && Date.parse(week.start)<=now && now-Date.parse(week.start)<172800000 && Date.parse(week.end)>now) {
    reminders.push({id:`new-week:${week.start}`,title:'Новая неделя — новая трасса',detail:week.name,
      action:'Попробовать →',to:`/race-game?track=${encodeURIComponent(week.track_id)}&weekly=1`,priority:20,expires:Date.parse(week.end)});
  }
  return reminders.sort((a,b)=>b.priority-a.priority);
}

export function reminderAllowed(item: VisitReminder, userId: number | null, now: number): boolean {
  try {
    if (sessionStorage.getItem(`f1hub-reminders-closed:${userId ?? 'guest'}`)) return false;
    const until = Number(localStorage.getItem(`f1hub-reminder:${userId ?? 'guest'}:${item.id}`));
    return !Number.isFinite(until) || until<=now;
  } catch {return true}
}

export function dismissReminder(item: VisitReminder, userId: number | null, now: number) {
  try {sessionStorage.setItem(`f1hub-reminders-closed:${userId ?? 'guest'}`,'1')} catch { /* Optional storage. */ }
  try {localStorage.setItem(`f1hub-reminder:${userId ?? 'guest'}:${item.id}`,String(Math.min(item.expires,now+86400000)))} catch { /* Optional storage. */ }
}
