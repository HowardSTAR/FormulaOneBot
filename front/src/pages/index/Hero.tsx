import { Link } from 'react-router-dom';
import { AnimatedTrackMap } from '../../components/AnimatedTrackMap';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
import { upcomingSession, countdownLabel } from './home-session';

export default function Hero({ nextRace: race, schedule, userTz, loaded, onRetry }: {
  nextRace: NextRaceResponse | null; schedule: SessionItem[]; userTz: string; loaded: boolean; onRetry: () => void;
}) {
  const now = useVisibleClock(30000, race?.status === 'ok');
  const upcoming = upcomingSession(schedule, race, now);
  if (!race && !loaded) return <section className="home-race home-panel home-race-state" aria-busy="true" aria-label="Ближайший этап"><p className="home-eyebrow">Ближайший этап</p><h2 role="status">Загружаем уик-энд…</h2><p>Расписание и трасса появятся здесь.</p></section>;
  if (race?.status === 'error' || !race) return <section className="home-race home-panel home-race-state"><p className="home-eyebrow">Ближайший этап</p><h2>Расписание недоступно</h2><p>Попробуйте загрузить данные ещё раз.</p><button className="home-button" type="button" onClick={onRetry}>Повторить загрузку</button></section>;
  const finished = race.status === 'season_finished';
  const title = finished ? `До встречи в ${(race.season || new Date().getFullYear()) + 1}` : race.event_name || 'Название уточняется';
  const date = upcoming?.utc_iso || race.race_start_utc || race.date;
  const validDate = date && Number.isFinite(Date.parse(date)) ? date : null;
  return <section className={`home-race home-panel${upcoming ? ' home-race--upcoming' : ''}`} aria-labelledby="home-race-title">
    <div className="home-race-meta"><span aria-label={upcoming ? `Ближайшая сессия: ${upcoming.name}` : undefined}>{finished ? 'Сезон завершён' : race.is_cancelled ? 'Этап отменён' : upcoming?.name || 'Ближайший этап'}</span>{race.round && !finished && <span>Этап {String(race.round).padStart(2, '0')}</span>}</div>
    <div className="home-race-content"><div className="home-race-copy"><h2 id="home-race-title"><Link to={finished || race.is_cancelled ? '/season' : '/next-race'} className="home-race-title-link" aria-label={`${finished || race.is_cancelled ? 'Календарь' : 'Уик-энд'}: ${title}`} data-analytics-action="session_open">{title}</Link></h2>
      <p className="home-race-location">{finished ? 'Результаты сезона — в зачёте ниже' : [race.location, race.country].filter(Boolean).join(' · ') || 'Место уточняется'}</p>
      {validDate && !finished && !race.is_cancelled && <time className="home-race-date" dateTime={validDate}>{new Date(validDate).toLocaleDateString('ru-RU', { timeZone: userTz, day: 'numeric', month: 'long' })}</time>}
    </div>{!finished && race.event_name && <div className="home-circuit" aria-hidden="true"><AnimatedTrackMap eventName={race.event_name} location={race.location} season={race.season} className="home-circuit-map" svgClassName="home-circuit-svg" loadingClassName="home-circuit-loading" /></div>}</div>
    <div className="home-race-bottom"><div className="home-next-session"><span>{race.is_cancelled ? 'Сессии не состоятся' : finished ? 'Спасибо за этот сезон' : upcoming ? 'До ближайшей сессии' : 'Расписание и результаты'}</span>
      {!finished && !race.is_cancelled && upcoming?.utc_iso && <strong>{countdownLabel(upcoming.utc_iso, now)}</strong>}
    </div></div>
  </section>;
}
