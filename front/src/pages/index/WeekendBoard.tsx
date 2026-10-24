import { Link } from 'react-router-dom';
import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
import { formatTimezoneLabel } from '../../helpers/timezone';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import { orderedSessions, upcomingSession } from './home-session';
import { HomeIcon } from './HomeIcon';

export function WeekendBoard({ race, sessions, timezone, loaded, onRetry }: {
  race: NextRaceResponse | null; sessions: SessionItem[]; timezone: string; loaded: boolean; onRetry: () => void;
}) {
  const now = useVisibleClock(30000);
  const inactive = race?.is_cancelled || race?.status === 'season_finished';
  const unavailable = inactive || race?.status === 'error';
  const timed = orderedSessions(sessions);
  const untimed = sessions.filter(session => !session.utc_iso || !Number.isFinite(Date.parse(session.utc_iso)));
  const rows = unavailable ? [] : [...timed, ...untimed];
  const next = upcomingSession(sessions, race, now);
  const details = race?.round ? `/next-race?season=${race.season}&round=${race.round}` : '/next-race';
  const status = !loaded ? 'Загружаем расписание…'
    : race?.is_cancelled ? 'Этап отменён'
    : race?.status === 'season_finished' ? 'Все этапы завершены'
    : next?.utc_iso ? `${next.name} · ${new Date(next.utc_iso).toLocaleString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}`
    : rows.length ? 'Даты, время и все сессии этапа' : 'Расписание пока недоступно';

  return <details className="home-schedule" key={`${race?.season}:${race?.round}:${race?.status}`}>
    <summary><HomeIcon name="calendar" /><span><strong>Расписание уик-энда</strong><small>{status}</small></span><HomeIcon name="chevronDown" /></summary>
    <div className="home-schedule-content">
      <p className="home-timezone">Время на вашем устройстве: {formatTimezoneLabel(timezone)}</p>
      <ol className="home-sessions">{rows.map((session, index) => {
        const date = session.utc_iso && Number.isFinite(Date.parse(session.utc_iso)) ? new Date(session.utc_iso) : null;
        const isNext = session.utc_iso === next?.utc_iso && session.name === next?.name;
        return <li key={`${session.name}:${session.utc_iso}:${index}`}>
          <Link to={details} data-analytics-action="session_open" className={isNext ? 'is-next' : undefined}>
            <span className="home-session-name">{session.name}{isNext && <small>Ближайшая сессия</small>}</span>
            {date ? <time dateTime={session.utc_iso}><span>{date.toLocaleDateString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'short' })}</span><strong>{date.toLocaleTimeString('ru-RU', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })}</strong></time> : <span className="home-session-unconfirmed">Время уточняется</span>}
          </Link>
        </li>;
      })}</ol>
      {!rows.length && <div className="home-empty" role="status">
        <p>{inactive ? 'Другие этапы и даты — в календаре сезона.' : !loaded ? 'Загружаем расписание…' : 'Подробное расписание пока недоступно. Попробуйте обновить данные.'}</p>
        {loaded && !inactive && <button type="button" className="home-text-action" onClick={onRetry}>Обновить расписание</button>}
        {inactive && <Link to="/season" className="home-text-action">Открыть календарь</Link>}
      </div>}
    </div>
  </details>;
}
