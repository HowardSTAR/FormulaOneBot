import { Link } from 'react-router-dom';
import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
import { formatTimezoneLabel } from '../../helpers/timezone';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import { orderedSessions } from './home-session';
import { HomeIcon } from './HomeIcon';

export function WeekendBoard({ race, sessions, timezone, loaded }: {
  race: NextRaceResponse | null; sessions: SessionItem[]; timezone: string; loaded: boolean;
}) {
  const now = useVisibleClock(30000);
  const unavailable = race?.is_cancelled || race?.status === 'season_finished' || race?.status === 'error';
  const rows = unavailable ? [] : orderedSessions(sessions);
  const next = rows.find(session => Date.parse(session.utc_iso) > now);
  const details = race?.round ? `/next-race?season=${race.season}&round=${race.round}` : '/next-race';
  return <section className="home-schedule home-panel" aria-labelledby="home-schedule-title">
    <header className="home-section-head"><h2 id="home-schedule-title">Расписание</h2><Link to="/season" data-analytics-action="calendar_open">Календарь <span aria-hidden="true">↗</span></Link></header>
    <p className="home-timezone">{formatTimezoneLabel(timezone)}</p>
    <ol className="home-sessions">{rows.map(session => {
      const date = new Date(session.utc_iso);
      return <li key={`${session.name}:${session.utc_iso}`}><Link to={details} data-analytics-action="session_open" className={session === next ? 'is-next' : undefined}>
        <span className="home-session-day"><strong>{date.toLocaleDateString('ru-RU', { timeZone: timezone, weekday: 'short' })}</strong><span>{date.toLocaleDateString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'short' }).replace(/\.$/, '')}</span></span>
        <span className="home-session-name">{session.name}{session === next && <small>Следующая сессия</small>}</span><time dateTime={session.utc_iso}>{date.toLocaleTimeString('ru-RU', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })}</time>
      </Link></li>;
    })}</ol>
    {!rows.length && <p className="home-empty" role="status">{!loaded ? 'Загружаем расписание…' : race?.is_cancelled ? 'Этап отменён. Другие этапы — в календаре.' : race?.status === 'season_finished' ? 'Все этапы сезона завершены.' : race?.status === 'error' ? 'Не удалось загрузить расписание.' : 'Расписание пока не опубликовано.'}</p>}
  </section>;
}
export function QuickAccess() {
  const links = [
    { to: '/race-results', icon: 'results', title: 'Результаты', text: 'Каждая сессия в деталях', action: 'results_open' },
    { to: '/compare', icon: 'compare', title: 'Сравнение пилотов', text: 'Кто быстрее на дистанции', action: 'compare_open' },
    { to: '/wiki', icon: 'wiki', title: 'Справочник', text: 'Ближе к пониманию гонок', action: 'wiki_open' },
  ] as const;
  return <nav className="home-explore" aria-label="Исследовать чемпионат">{links.map(item => <Link className="home-panel" key={item.to} to={item.to} data-analytics-action={item.action}><HomeIcon name={item.icon} /><span><strong>{item.title}</strong><small>{item.text}</small></span><span className="home-explore-arrow" aria-hidden="true">↗</span></Link>)}</nav>;
}
