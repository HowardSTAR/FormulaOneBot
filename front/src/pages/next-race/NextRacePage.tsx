import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AnimatedTrackMap } from '../../components/AnimatedTrackMap';
import { DetailedTrackMap } from '../../components/DetailedTrackMap';
import { CalendarDownload } from '../../components/CalendarDownload';
import { GlossaryText } from '../../components/GlossaryText';
import { getCircuitInsightsRu } from '../../assets/circuitInsightsRu';
import { apiRequest } from '../../helpers/api';
import { getDisplayTimezone, formatTimezoneLabel } from '../../helpers/timezone';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
import { availableResults, sessionStart, sortedWeekend, stageSelection, type StageSelection } from './weekend-model';
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
  return <header className="weekend-heading"><div><p className="weekend-eyebrow">Всё для гоночных выходных{season ? ` · ${season}` : ''}</p><h1>Уик-энд</h1></div><Link to="/season" className="weekend-secondary">Календарь <span aria-hidden="true">↗</span></Link></header>;
}

function WeekendContent({ selection }: { selection: Exclude<StageSelection, { kind: 'invalid' }> }) {
  const season = selection.kind === 'selected' ? selection.season : null;
  const round = selection.kind === 'selected' ? selection.round : null;
  const [state, setState] = useState<State>({ status: 'loading' });
  const [revision, setRevision] = useState(0);
  const timezone = getDisplayTimezone();
  const now = useVisibleClock(30000);
  const retry = () => { setState({ status: 'loading' }); setRevision(value => value + 1); };

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

  if (state.status === 'loading') return <main className="weekend-page"><WeekendHeading season={season ?? undefined} /><WeekendStatus title="Загружаем уик-энд…" message="Расписание, старт гонки и схема трассы появятся здесь." loading /></main>;
  if (state.status === 'error') return <main className="weekend-page"><WeekendHeading /><WeekendStatus title="Не удалось загрузить этап" message={state.message} retry={retry} /></main>;
  const { race, sessions, scheduleFailed } = state;
  if (race.status === 'season_finished') return <main className="weekend-page"><WeekendHeading season={race.season} /><WeekendStatus title="Сезон завершён" message="Результаты прошедших этапов доступны в календаре. До встречи в новом сезоне." /></main>;

  const next = sessions.find(session => (sessionStart(session) ?? -Infinity) > now);
  const raceSession = sessions.find(session => /^(гонка|race)$/i.test(session.name.trim()));
  const start = raceSession?.utc_iso || race.race_start_utc;
  const raceStart = start && sessionStart({ name: 'Гонка', utc_iso: start }) !== null ? start : null;
  const publishedDate = /^\d{4}-\d{2}-\d{2}$/.test(race.date || '') && Number.isFinite(Date.parse(race.date!)) ? race.date : null;
  const results = race.is_cancelled ? [] : availableResults(sessions, now);
  const query = `?mode=archive&season=${race.season}&round=${race.round}`;
  const insights = getCircuitInsightsRu({ season: race.season, eventName: race.event_name || '', country: race.country || '', location: race.location || '', eventFormat: race.event_format, sessionsCount: sessions.length });

  return <main className="weekend-page">
    <WeekendHeading season={race.season} />
    <section className="weekend-hero weekend-panel" aria-labelledby="weekend-race-title">
      <div className="weekend-hero-copy">
        <p className="weekend-eyebrow">{race.is_cancelled ? 'Этап отменён' : race.round ? `Этап ${String(race.round).padStart(2, '0')}` : 'Гоночный уик-энд'}</p>
        <h2 id="weekend-race-title">{race.event_name || 'Название уточняется'}</h2>
        <p className="weekend-location">{[race.location, race.country].filter(Boolean).join(' · ') || 'Место уточняется'}</p>
        <div className="weekend-race-start"><span>{race.is_cancelled ? 'Статус' : 'Старт гонки'}</span>
          {race.is_cancelled ? <strong>Отменён организатором</strong> : raceStart ? <time dateTime={raceStart}><strong>{new Date(raceStart).toLocaleDateString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long' })}</strong><span>{new Date(raceStart).toLocaleTimeString('ru-RU', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })} · {formatTimezoneLabel(timezone)}</span></time> : publishedDate ? <time dateTime={publishedDate}><strong>{new Date(publishedDate).toLocaleDateString('ru-RU', { timeZone: 'UTC', day: 'numeric', month: 'long' })}</strong><span>Время уточняется</span></time> : <strong>Время уточняется</strong>}
        </div>
      </div>
      <div className="weekend-track">
        <div className="weekend-track-heading"><span>Схема трассы</span><span>{race.location}</span></div>
        {race.event_name ? <DetailedTrackMap key={`${race.event_name}:${race.season}`} eventName={race.event_name} location={race.location} season={race.season ?? 0} preview={<AnimatedTrackMap eventName={race.event_name} location={race.location} season={race.season} className="weekend-track-map" svgClassName="weekend-track-svg" loadingClassName="weekend-track-loading" />} /> : <p>Схема появится после публикации этапа.</p>}
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
          return <li key={`${session.name}:${session.utc_iso || index}`} className={session === next ? 'is-next' : undefined}>
            <span className="weekend-session-day">{date ? <><strong>{date.toLocaleDateString('ru-RU', { timeZone: timezone, weekday: 'short' })}</strong><span>{date.toLocaleDateString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'short' }).replace(/\.$/, '')}</span></> : 'Дата уточняется'}</span>
            <span className="weekend-session-name">{session.name}{session === next && <small>Следующая сессия</small>}</span>
            {date ? <time dateTime={session.utc_iso}>{date.toLocaleTimeString('ru-RU', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })}</time> : <span className="weekend-time-pending">Время уточняется</span>}
          </li>;
        })}
      </ol>}
    </section>

    {!race.is_cancelled && <section className="weekend-results weekend-panel" aria-labelledby="weekend-results-title"><header className="weekend-section-head"><h2 id="weekend-results-title">Результаты этапа</h2><span>Классификация сессий</span></header>
      {results.length && race.season && race.round ? <nav aria-label="Результаты сессий">{results.map(result => <Link className="weekend-secondary" key={result.path} to={`${result.path}${query}`}>{result.title} <span aria-hidden="true">↗</span></Link>)}</nav> : <p className="weekend-empty">Результаты появятся после проведения сессий.</p>}
      {results.length > 0 && <p className="weekend-results-note">Источник может опубликовать результаты с задержкой после финиша.</p>}
    </section>}

    <section className="weekend-insights" aria-labelledby="weekend-insights-title"><h2 id="weekend-insights-title">Знакомство с трассой</h2>
      <dl className="weekend-stats">{insights.stats.map(stat => <div className="weekend-panel" key={stat.label}><dt>{stat.label}</dt><dd>{stat.value}</dd>{stat.hint && <p>{stat.hint}</p>}</div>)}</dl>
      {insights.facts.length > 0 && <div className="weekend-facts weekend-panel">{insights.facts.map(fact => <details key={fact.title}><summary>{fact.title}</summary><p><GlossaryText>{fact.text}</GlossaryText></p></details>)}</div>}
    </section>
  </main>;
}

export default function NextRacePage() {
  const [params] = useSearchParams();
  const selection = stageSelection(params.get('season'), params.get('round'));
  if (selection.kind === 'invalid') return <main className="weekend-page"><WeekendHeading /><WeekendStatus title="Этап не найден" message="В ссылке указан некорректный сезон или номер этапа. Выберите этап в календаре." /></main>;
  return <WeekendContent key={selection.kind === 'selected' ? `${selection.season}:${selection.round}` : 'next'} selection={selection} />;
}
