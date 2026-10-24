import { Link } from 'react-router-dom';
import { AnimatedTrackMap } from '../../components/AnimatedTrackMap';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import { formatTimezoneLabel } from '../../helpers/timezone';
import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
import { countdownLabel, raceStart } from './home-session';
import { HomeIcon } from './HomeIcon';

export default function Hero({ nextRace: race, schedule, userTz, loaded, onRetry }: {
  nextRace: NextRaceResponse | null; schedule: SessionItem[]; userTz: string; loaded: boolean; onRetry: () => void;
}) {
  const now = useVisibleClock(30000, race?.status === 'ok');
  if (!race && !loaded) {
    return <section className="home-race home-race-state" aria-busy="true" aria-label="Ближайшая гонка">
      <p className="home-eyebrow">Ближайшая гонка</p><h2 role="status">Загружаем уик-энд…</h2>
      <p>Дата старта и расписание появятся здесь.</p>
    </section>;
  }
  if (race?.status === 'error' || !race) {
    return <section className="home-race home-race-state">
      <p className="home-eyebrow">Ближайшая гонка</p><h2>Не удалось загрузить этап</h2>
      <p>Проверьте подключение и повторите загрузку.</p>
      <button className="home-race-cta" type="button" onClick={onRetry}>Повторить загрузку</button>
    </section>;
  }
  const finished = race.status === 'season_finished';
  const cancelled = Boolean(race.is_cancelled);
  const inactive = finished || cancelled;
  const title = finished ? 'Сезон завершён' : race.event_name || 'Название этапа уточняется';
  const start = raceStart(schedule, race);
  const date = start ? new Date(start) : null;
  const upcoming = !inactive && Boolean(start && Date.parse(start) > now);
  const countdown = cancelled ? 'Этап отменён. Выберите другую гонку в календаре.'
    : finished ? 'Итоги чемпионата — в зачёте ниже.'
    : start ? Date.parse(start) > now ? countdownLabel(start, now) : 'Плановое время старта прошло'
    : 'Время старта уточняется';

  return <section className={`home-race${inactive ? ' home-race--inactive' : ''}`} aria-labelledby="home-race-title">
    <div className="home-race-copy">
      <h2 id="home-race-title">{title}</h2>
      {!finished && <p className="home-race-location"><span>{[race.location, race.country].filter(Boolean).join(' · ') || 'Место уточняется'}</span>{race.round && <span>Этап {race.round}</span>}</p>}
    </div>
    {!inactive && <div className="home-race-details">
      <div className="home-race-ticket">
        <span className="home-ticket-label">Старт гонки</span>
        {date && start ? <time className="home-race-date" dateTime={start}>
          <span>{date.toLocaleDateString('ru-RU', { timeZone: userTz, day: 'numeric', month: 'long', weekday: 'short' })}</span>
          <strong>{date.toLocaleTimeString('ru-RU', { timeZone: userTz, hour: '2-digit', minute: '2-digit' })}</strong>
          <small className="home-ticket-timezone">{formatTimezoneLabel(userTz)}</small>
        </time> : <><p className="home-race-unconfirmed">Расписание уточняется</p><span className="home-ticket-timezone">{formatTimezoneLabel(userTz)}</span></>}
      </div>
      {race.event_name && <div className="home-circuit" aria-hidden="true">
        <AnimatedTrackMap eventName={race.event_name} location={race.location} season={race.season} className="home-circuit-map" svgClassName="home-circuit-svg" loadingClassName="home-circuit-loading" />
      </div>}
    </div>}
    <div className="home-race-actions">
      <p className={`home-race-countdown${upcoming ? ' home-race-countdown--upcoming' : ''}`}>{upcoming && <HomeIcon name="clock" />}<span>{countdown}</span></p>
      {inactive && <Link to="/season" className="home-race-cta" data-analytics-action="calendar_open">Открыть календарь <span aria-hidden="true">↗</span></Link>}
    </div>
  </section>;
}
