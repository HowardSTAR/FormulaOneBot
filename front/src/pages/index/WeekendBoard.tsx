import { Link } from 'react-router-dom';
import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
import { formatTimezoneLabel } from '../../helpers/timezone';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import IndexIcon from './IndexIcon';
import './weekend-board.css';

export function WeekendBoard({ race, sessions, timezone, total, loaded }: {
  race: NextRaceResponse | null; sessions: SessionItem[]; timezone: string; total: number; loaded: boolean;
}) {
  const now = useVisibleClock(30000);
  const rows = sessions.filter(s => s.utc_iso && Number.isFinite(Date.parse(s.utc_iso)))
    .map(s => ({ ...s, date: new Date(s.utc_iso!) })).sort((a, b) => +a.date - +b.date);
  const active = rows.find(s => now >= +s.date && now < +s.date + 90 * 60000)
    || rows.find(s => +s.date > now);
  const details = race?.round ? `/race-details?season=${race.season}&round=${race.round}` : '/next-race';
  return <section className="weekend-board">
    <div className="weekend-board-top"><span>Этап {race?.round || '—'}{total > 0 ? ` из ${total}` : ''}</span>
      <Link to="/season" data-analytics-action="calendar_open">Весь сезон →</Link></div>
    <h2>Расписание уик-энда</h2>
    <div className="weekend-board-location"><span>📍 {race?.location || race?.country || 'Место уточняется'}</span>
      <span>Время: {formatTimezoneLabel(timezone)}</span></div>
    <div className="weekend-board-sessions">{rows.map(s => <Link key={`${s.name}:${s.utc_iso}`} to={details}
      data-analytics-action="session_open" className={`weekend-board-row${s === active ? ' is-current' : ''}`}>
      <span className="weekend-board-date"><strong>{s.date.toLocaleDateString('ru-RU', {timeZone: timezone, weekday: 'short'})}</strong>
        <span>{s.date.toLocaleDateString('ru-RU', {timeZone: timezone, day: 'numeric', month: 'short'}).replace(/\.$/, '')}</span></span>
      <span className="weekend-board-session">{s.name}{s === active && now >= +s.date && <small>Старт по расписанию</small>}</span>
      <time dateTime={s.utc_iso}>{s.date.toLocaleTimeString('ru-RU', {timeZone: timezone, hour: '2-digit', minute: '2-digit'})}</time>
      <span className="weekend-board-arrow" aria-hidden>›</span>
    </Link>)}</div>
    {!rows.length && <p>{!loaded ? 'Загружаем расписание…' : 'Расписание пока не опубликовано.'}</p>}
    {!rows.length && loaded && <Link className="ui-action-link" to="/season">Открыть календарь →</Link>}
  </section>;
}

export function QuickAccess({season}: {season: number}) {
  const links = [
    {to: '/season', icon: 'calendar' as const, title: 'Календарь сезона', text: `Все этапы ${season} года`, action: 'calendar_open'},
    {to: '/race-results', icon: 'results' as const, title: 'Результаты', text: 'Гонки, квалификации и практики', action: 'results_open'},
    {to: '/compare', icon: 'compare' as const, title: 'Сравнение пилотов', text: 'Очки, статистика и результаты', action: 'compare_open'},
    {to: '/history', icon: 'analytics' as const, title: 'История чемпионата', text: 'Графики пилотов и команд по сезонам', action: 'history_open'},
    {to: '/wiki', icon: 'wiki' as const, title: 'Справочник F1', text: 'Термины и правила простыми словами', action: 'wiki_open'},
  ];
  return <section className="quick-access"><h2>Быстрый доступ</h2><div>{links.map(item =>
    <Link key={item.to} to={item.to} data-analytics-action={item.action}><IndexIcon name={item.icon}/>
      <span><strong>{item.title}</strong><small>{item.text}</small></span><b aria-hidden>›</b></Link>)}</div></section>;
}
