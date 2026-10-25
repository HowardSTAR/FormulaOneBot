import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AnimatedTrackMap } from '../../components/AnimatedTrackMap';
import { DetailedTrackMap } from '../../components/DetailedTrackMap';
import { CalendarDownload } from '../../components/CalendarDownload';
import { getCircuitInsightsRu } from '../../assets/circuitInsightsRu';
import { apiRequest } from '../../helpers/api';
import { getDisplayTimezone, formatTimezoneLabel } from '../../helpers/timezone';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
import { sessionStart, sortedWeekend, stageSelection, weekendSession, weekendSessionLink, type StageSelection } from './weekend-model';
import { WeekendCircuitInfo, WeekendCircuitStats } from './WeekendCircuitInfo';
import { WeekendSessionResults } from './WeekendSessionResults';
import { useCircuitProfile } from './useCircuitProfile';
import './weekend.css';

type Race = NextRaceResponse & { sessions?: SessionItem[]; event_format?: string };
type Loaded = { race: Race; sessions: SessionItem[]; scheduleFailed: boolean };
type State = { status: 'loading' } | { status: 'error'; message: string } | ({ status: 'ready' } & Loaded);

function WeekendStatus({ title, message, retry, loading = false }: { title: string; message: string; retry?: () => void; loading?: boolean }) {
  return <section className="weekend-status weekend-panel" aria-busy={loading} role={retry ? 'alert' : undefined}>
    <h2>{title}</h2><p role={loading ? 'status' : undefined}>{message}</p>
    <div>{retry && <button type="button" className="weekend-button" onClick={retry}>Повторить загрузку</button>}<Link className="weekend-secondary" to="/season">Открыть календарь <span aria-hidden="true">↗</span></Link></div>
  </section>;
}

function WeekendHeading({ season }: { season?: number }) {
  return <header className="weekend-heading"><h1 tabIndex={-1}>Уик-энд{season && <span className="weekend-season">{season}</span>}</h1><Link to="/season" className="weekend-secondary">Календарь <span aria-hidden="true">↗</span></Link></header>;
}

function WeekendContent({ selection }: { selection: Exclude<StageSelection, { kind: 'invalid' }> }) {
  const [params] = useSearchParams();
  const season = selection.kind === 'selected' ? selection.season : null;
  const round = selection.kind === 'selected' ? selection.round : null;
  const [state, setState] = useState<State>({ status: 'loading' });
  const [revision, setRevision] = useState(0);
  const selectedSession = params.get('session');
  const previousSession = useRef(selectedSession);
  const timezone = getDisplayTimezone();
  const now = useVisibleClock(30000);
  const retry = () => { setState({ status: 'loading' }); setRevision(value => value + 1); };

  useEffect(() => {
    if (previousSession.current && !selectedSession) document.querySelector<HTMLElement>('.weekend-heading h1')?.focus();
    previousSession.current = selectedSession;
  }, [selectedSession]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const race: Race = season && round
          ? { ...await apiRequest<Race>('/api/race-details', { season, round }), status: 'ok', season, round }
          : await apiRequest<Race>('/api/next-race');
        if (race.status === 'season_finished') {
          if (active) setState({ status: 'ready', race, sessions: [], scheduleFailed: false });
          return;
        }
        if (race.status !== 'ok') throw new Error('Не удалось получить сведения об этапе.');
        let sessions = race.sessions || [];
        let scheduleFailed = false;
        if (!season && !race.is_cancelled && race.season && race.round) {
          try {
            const schedule = await apiRequest<{ sessions?: SessionItem[] }>('/api/weekend-schedule', { season: race.season, round_number: race.round });
            sessions = schedule.sessions || [];
          } catch { scheduleFailed = true; }
        }
        if (active) setState({ status: 'ready', race, sessions: sortedWeekend(sessions), scheduleFailed });
      } catch (error) {
        if (active) setState({ status: 'error', message: error instanceof Error ? error.message : 'Не удалось загрузить этап.' });
      }
    };
    void load();
    return () => { active = false; };
  }, [season, round, revision]);

  const profileState = useCircuitProfile(state.status === 'ready' ? state.race.season : undefined, state.status === 'ready' ? state.race.round : undefined, state.status === 'ready' ? state.race.event_name : undefined);

  if (state.status === 'loading') return <main className="weekend-page"><WeekendHeading season={season ?? undefined} /><WeekendStatus title="Загружаем уик-энд…" message="Расписание, старт гонки и схема трассы появятся здесь." loading /></main>;
  if (state.status === 'error') return <main className="weekend-page"><WeekendHeading /><WeekendStatus title="Не удалось загрузить этап" message={state.message} retry={retry} /></main>;
  const { race, sessions, scheduleFailed } = state;
  if (race.status === 'season_finished') return <main className="weekend-page"><WeekendHeading season={race.season} /><WeekendStatus title="Сезон завершён" message="Результаты прошедших этапов доступны в календаре. До встречи в новом сезоне." /></main>;

  const next = sessions.find(session => (sessionStart(session) ?? -Infinity) > now);
  const raceSession = sessions.find(session => /^(гонка|race)$/i.test(session.name.trim()));
  const start = raceSession?.utc_iso || race.race_start_utc;
  const raceStart = start && sessionStart({ name: 'Гонка', utc_iso: start }) !== null ? start : null;
  const publishedDate = /^\d{4}-\d{2}-\d{2}$/.test(race.date || '') && Number.isFinite(Date.parse(race.date!)) ? race.date : null;
  const insights = getCircuitInsightsRu({ season: race.season, eventName: race.event_name || '', country: race.country || '', location: race.location || '', eventFormat: race.event_format, sessionsCount: sessions.length });
  const circuitProfile = profileState.profile;

  if (selectedSession && !race.is_cancelled && race.season && race.round) return <WeekendSessionResults
    key={`${race.season}:${race.round}:${selectedSession}`} selected={selectedSession} now={now}
    season={race.season} round={race.round} eventName={race.event_name || 'Этап'} sessions={sessions} />;
  const dated = sessions.flatMap(session => { const start = sessionStart(session); return start === null ? [] : [start]; });
  const weekendDates = dated.length ? new Intl.DateTimeFormat('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long' }).formatRange(new Date(Math.min(...dated)), new Date(Math.max(...dated))) : null;

  return <main className="weekend-page">
    <WeekendHeading season={race.season} />
    <section className="weekend-hero" aria-labelledby="weekend-race-title">
      <div className="weekend-hero-copy">
        <h2 id="weekend-race-title">{race.event_name || 'Название уточняется'}</h2>
        <p className="weekend-location"><span>{[race.location, race.country].filter(Boolean).join(' · ') || 'Место уточняется'}</span>{race.round && <span>Этап {race.round}</span>}</p>
        {weekendDates && <p className="weekend-dates">{weekendDates}</p>}
      </div>
      <div className="weekend-circuit-summary">
        <WeekendCircuitStats insights={insights} limit={3} />
      </div>
      <div className="weekend-race-start"><span>{race.is_cancelled ? 'Статус' : 'Старт гонки'}</span>
        {race.is_cancelled ? <strong>Отменён организатором</strong> : raceStart ? <time dateTime={raceStart}><span className="weekend-start-date">{new Date(raceStart).toLocaleDateString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long' })}</span><strong className="weekend-start-time">{new Date(raceStart).toLocaleTimeString('ru-RU', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })}</strong><span className="weekend-timezone">{formatTimezoneLabel(timezone)}</span></time> : publishedDate ? <time dateTime={publishedDate}><strong>{new Date(publishedDate).toLocaleDateString('ru-RU', { timeZone: 'UTC', day: 'numeric', month: 'long' })}</strong><span className="weekend-timezone">Время уточняется</span></time> : <strong>Время уточняется</strong>}
      </div>
      <div className="weekend-track">
        {race.event_name ? <DetailedTrackMap key={`${race.event_name}:${race.season}`} eventName={race.event_name} location={race.location} season={race.season ?? 0} triggerLabel="Статистика трассы" dialogTitle={circuitProfile?.name} preview={<AnimatedTrackMap fitRoute animate={false} eventName={race.event_name} location={race.location} season={race.season} className="weekend-track-map" svgClassName="weekend-track-svg" loadingClassName="weekend-track-loading" />}><WeekendCircuitInfo insights={insights} profile={circuitProfile} season={race.season ?? 0} loading={profileState.loading} error={profileState.error} retry={profileState.retry} /></DetailedTrackMap> : <p>Схема появится после публикации этапа.</p>}
      </div>
    </section>

    <section className="weekend-schedule weekend-panel" aria-labelledby="weekend-schedule-title">
      <header className="weekend-section-head"><div><h2 id="weekend-schedule-title">Расписание сессий</h2><p>{formatTimezoneLabel(timezone)} · все даты в вашем часовом поясе</p></div>
        {!race.is_cancelled && <CalendarDownload title={race.event_name || 'Этап'} season={race.season ?? 0} round={race.round ?? 0} sessions={sessions} />}
      </header>
      {race.is_cancelled ? <p className="weekend-empty">Этап отменён. Сессии не состоятся.</p> : scheduleFailed ? <div className="weekend-empty" role="status"><p>Сведения об этапе загружены, но расписание сейчас недоступно.</p><button type="button" className="weekend-secondary" onClick={retry}>Повторить загрузку</button></div> : !sessions.length ? <p className="weekend-empty">Расписание пока не опубликовано.</p> : <ol className="weekend-timetable">
        {sessions.map((session, index) => {
          const timestamp = sessionStart(session);
          const date = timestamp !== null ? new Date(timestamp) : null;
          const target = weekendSession(session.name);
          const resultLink = !race.is_cancelled && date && timestamp! <= now && target && race.season && race.round
            ? weekendSessionLink(race.season, race.round, session.name) : null;
          const content = <>
            <span className="weekend-session-day">{date ? <><strong>{date.toLocaleDateString('ru-RU', { timeZone: timezone, day: 'numeric' })}</strong><span>{date.toLocaleDateString('ru-RU', { timeZone: timezone, weekday: 'short', month: 'short' })}</span></> : 'Дата уточняется'}</span>
            <span className="weekend-session-name">{session.name}<span className="weekend-session-start">{date ? <time dateTime={session.utc_iso}>{date.toLocaleTimeString('ru-RU', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })}</time> : 'Время уточняется'}</span>{session === next && <small>Следующая сессия</small>}</span>
            {resultLink && <span className="weekend-session-result">Результаты <span aria-hidden="true">›</span></span>}
          </>;
          return <li key={`${session.name}:${session.utc_iso || index}`} className={session === next ? 'is-next' : undefined}>
            {resultLink ? <Link to={resultLink} className="weekend-session-row" aria-label={`${session.name}: результаты`}>{content}</Link> : <div className="weekend-session-row">{content}</div>}
          </li>;
        })}
      </ol>}
    </section>
  </main>;
}

export default function NextRacePage() {
  const [params] = useSearchParams();
  const selection = stageSelection(params.get('season'), params.get('round'));
  if (selection.kind === 'invalid') return <main className="weekend-page"><WeekendHeading /><WeekendStatus title="Этап не найден" message="В ссылке указан некорректный сезон или номер этапа. Выберите этап в календаре." /></main>;
  return <WeekendContent key={selection.kind === 'selected' ? `${selection.season}:${selection.round}` : 'next'} selection={selection} />;
}
