import { localDateTime, optionalNumber, timezoneName } from '../../helpers/presentation';
import { useState, useEffect, useCallback, useMemo, useRef, useLayoutEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatedTrackMap } from "../../components/AnimatedTrackMap";
import { BackButton } from "../../components/BackButton";
import { YearSelect } from "../../components/YearSelect";
import { apiRequest } from "../../helpers/api";
import { getDisplayTimezone } from "../../helpers/timezone";
import { getCircuitInsightsRu } from "../../assets/circuitInsightsRu";
import { visibleInterval } from "../../helpers/visibleInterval";
import { PageFeedback } from '../../components/PageFeedback';
import { GlossaryText } from '../../components/GlossaryText';
import { calendarState as getCalendarState, calendarStatusLabel, filteredCalendar, isCompletedStatus,
  parseRaceTime, readCalendarQuery, selectedCalendarRace, raceDateParts, raceSessions, calendarResultLinks } from '../../helpers/seasonCalendar';
import type { CalendarRace as Race, CalendarFilter } from '../../helpers/seasonCalendar';
import { GlassSwitch } from '../index/GlassSwitch';
import { RaceFlagBackdrop } from '../../components/RaceFlagBackdrop';
import '../index/home-controls.css';
import './season.css';

const currentRealYear = new Date().getFullYear();

type SeasonResponse = { races?: Race[] };
type RaceResult = {
  position: number;
  code: string;
  name: string;
  team: string;
  points: number;
};
type RaceResultsResponse = {
  season?: number;
  round?: number | null;
  results?: RaceResult[];
  data_incomplete?: boolean;
};
type PodiumState = {
  loading: boolean;
  error: string | null;
  results: RaceResult[];
};
const RACE_RESULTS_MIN_AGE_MS = 2 * 60 * 60 * 1000;

function SeasonPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const {year, round: selectedRound, filter} = readCalendarQuery(searchParams, currentRealYear);
  const calendarRequest = useRef(0);
  const [races, setRaces] = useState<Race[]>([]);
  const [loadedYear, setLoadedYear] = useState<number | null>(null);
  const userTz = getDisplayTimezone();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);
  const selectedHeading = useRef<HTMLHeadingElement>(null);
  const focusRound = useRef<number | null>(null);
  const [calendarNowMs, setCalendarNowMs] = useState(() => Date.now());
  const [latestReadyRound, setLatestReadyRound] = useState<number | null>(null);
  const [podiums, setPodiums] = useState<Record<number, PodiumState>>({});
  const activeRaces = loadedYear === year ? races : [];
  const isLoading = loading || loadedYear !== year;
  const filterParams = (value: CalendarFilter) => {
    const next = new URLSearchParams(searchParams);
    next.set('filter', value);
    if (!filteredCalendar(activeRaces, calendarState.statusByRound, value).some(race => race.round === selectedRound)) next.delete('round');
    return next;
  };
  const setFilter = (value: CalendarFilter) => setSearchParams(filterParams(value), { replace: true });

  const loadCalendar = useCallback(async (season: number) => {
    const request = ++calendarRequest.current;
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    setLatestReadyRound(null);
    setPodiums({});
    try {
      const data = await apiRequest<SeasonResponse>("/api/season", { season });
      if (request !== calendarRequest.current) return;
      if (!data.races || data.races.length === 0) {
        setRaces([]);
        setEmptyMessage("Расписание не найдено");
      } else {
        const loadedRaces = [...data.races].sort((a, b) => a.round - b.round);
        setRaces(loadedRaces);
      }
    } catch (e) {
      if (request !== calendarRequest.current) return;
      console.error(e);
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
      setRaces([]);
    } finally {
      if (request === calendarRequest.current) { setLoadedYear(season); setLoading(false); }
    }
  }, []);

  useEffect(() => {
    void loadCalendar(year);
    return () => { calendarRequest.current += 1; };
  }, [year, loadCalendar]);

  const updateYear = useCallback((y: number) => {
    setPodiums({});
    setSearchParams(y === currentRealYear ? {} : { year: String(y) }, { replace: true });
  }, [setSearchParams]);

  useEffect(() => {
    if (year !== currentRealYear || loadedYear !== year || races.length === 0) {
      setLatestReadyRound(null);
      return;
    }

    let cancelled = false;
    const refreshStatus = async () => {
      const nowMs = Date.now();
      if (cancelled) return;
      setCalendarNowMs(nowMs);
      const latestRaceStarted = [...races]
        .reverse()
        .find((race) => {
          const raceStart = parseRaceTime(race.race_start_utc);
          return !race.is_cancelled && raceStart !== null && raceStart <= nowMs;
        });

      if (!latestRaceStarted) {
        if (!cancelled) setLatestReadyRound(null);
        return;
      }

      const raceStart = parseRaceTime(latestRaceStarted.race_start_utc);
      if (raceStart === null || nowMs - raceStart < RACE_RESULTS_MIN_AGE_MS || nowMs - raceStart > 24 * 60 * 60 * 1000) {
        if (!cancelled) setLatestReadyRound(null);
        return;
      }

      try {
        const response = await apiRequest<RaceResultsResponse>("/api/race-results", {
          season: year,
          round: latestRaceStarted.round,
        });
        if (cancelled) return;
        const ready =
          response.round === latestRaceStarted.round &&
          (response.season == null || response.season === year) &&
          (response.results?.length || 0) >= 10 &&
          !response.data_incomplete;
        setLatestReadyRound(ready ? latestRaceStarted.round : null);
      } catch {
        // Сохраняем прошлое подтверждённое состояние и повторяем проверку через минуту.
      }
    };

    void refreshStatus();
    const stop = visibleInterval(() => void refreshStatus(), 60_000);
    return () => {
      cancelled = true;
      stop();
    };
  }, [races, year, loadedYear]);

  useEffect(() => visibleInterval(() => setCalendarNowMs(Date.now()), 60_000), []);

  const handleYearChange = (y: number) => {
    if (y > currentRealYear) {
      setEmptyMessage("Мы не умеем смотреть в будущее");
      setRaces([]);
      setLoading(false);
      return;
    }
    if (y < 1950) {
      setEmptyMessage("Тогда гонок ещё не было");
      setRaces([]);
      setLoading(false);
      return;
    }
    updateYear(y);
  };

  const calendarState = useMemo(() => getCalendarState(loadedYear === year ? races : [], year, calendarNowMs, latestReadyRound), [calendarNowMs, latestReadyRound, races, year, loadedYear]);
  const visibleRaces = filteredCalendar(activeRaces, calendarState.statusByRound, filter);
  const selectedRace = selectedCalendarRace(visibleRaces, selectedRound, filter, calendarState.statusByRound);
  const selectedStatus = selectedRace ? calendarState.statusByRound.get(selectedRace.round) : undefined;
  const completedRacesCount = filteredCalendar(activeRaces, calendarState.statusByRound, 'past').length;
  const upcomingRacesCount = filteredCalendar(activeRaces, calendarState.statusByRound, 'upcoming').length;
  const selectedInsights = selectedRace
    ? getCircuitInsightsRu({
        season: year,
        eventName: selectedRace.event_name,
        country: selectedRace.country ?? "",
        location: selectedRace.location,
        eventFormat: selectedRace.sprint_start_utc ? 'Со спринтом' : 'Стандартный',
        sessionsCount: raceSessions(selectedRace).filter(session => session.iso).length,
      })
    : null;

  const selectedDateLabel = selectedRace ? raceDateParts(selectedRace, userTz).label : '—';
  const selectedResultLinks = selectedRace ? calendarResultLinks(selectedRace, year, calendarNowMs, selectedStatus) : [];
  const formatSessionTime = (iso?: string | null): string => localDateTime(iso, userTz);
  const loadPodium = useCallback(async (round: number) => {
    const request = calendarRequest.current;
    if (podiums[round]?.loading || podiums[round]?.results.length) return;
    setPodiums((current) => ({
      ...current,
      [round]: { loading: true, error: null, results: [] },
    }));
    try {
      const response = await apiRequest<RaceResultsResponse>("/api/race-results", {
        season: year,
        round,
      });
      if (request !== calendarRequest.current) return;
      if (response.round !== round || (response.season != null && response.season !== year)) throw new Error('Источник вернул другой этап. Повторите загрузку.');
      const results = (response.data_incomplete ? [] : response.results || [])
        .filter((result) => result.position >= 1 && result.position <= 3)
        .sort((a, b) => a.position - b.position)
        .slice(0, 3);
      setPodiums((current) => ({
        ...current,
        [round]: {
          loading: false,
          error: results.length ? null : "Результаты этапа ещё обрабатываются",
          results,
        },
      }));
    } catch (e) {
      if (request !== calendarRequest.current) return;
      setPodiums((current) => ({
        ...current,
        [round]: {
          loading: false,
          error: e instanceof Error ? e.message : "Не удалось загрузить результаты",
          results: [],
        },
      }));
    }
  }, [podiums, year]);

  useLayoutEffect(() => {
    if (focusRound.current === selectedRace?.round) {
      focusRound.current = null;
      selectedHeading.current?.focus();
    }
  }, [selectedRace?.round]);

  const selectRace = (race: Race) => {
    if (selectedRace?.round === race.round) {
      selectedHeading.current?.focus();
      return;
    }
    focusRound.current = race.round;
    setSearchParams(previous => {
      const next = new URLSearchParams(previous);
      next.set('round', String(race.round));
      return next;
    }, { replace: true });
  };
  const selectedPodium = selectedRace ? podiums[selectedRace.round] : undefined;
  const selectedSessions = selectedRace ? raceSessions(selectedRace) : [];
  const filterLabel = filter === 'upcoming' ? 'Предстоящие этапы' : filter === 'past' ? 'Прошедшие этапы' : 'Все этапы';

  return (
    <div className="season-page">
      <BackButton>← <span>Главное меню</span></BackButton>
      <header className="calendar-heading">
        <div>
          <h1>Календарь</h1>
          <p>Гоночные уик-энды Формулы-1 · {year}</p>
        </div>
        <div className="calendar-year">
          <YearSelect value={year} onChange={handleYearChange} minYear={1950}
            maxYear={currentRealYear} ariaLabel="Сезон календаря" showCurrentYearBtn={year !== currentRealYear} />
        </div>
      </header>

      <div className="calendar-controls">
        <GlassSwitch className="calendar-filters" label="Фильтр календаря" selected={filter} replace
          items={([
            ['upcoming', 'Предстоящие', 'clock', upcomingRacesCount],
            ['past', 'Прошедшие', 'history', completedRacesCount],
            ['all', 'Весь сезон', 'calendar', activeRaces.length],
          ] as const).map(([value, label, icon, count]) => ({
            id: value, icon, label: !isLoading && !error ? `${label}: ${count}` : label,
            to: `/season?${filterParams(value)}`,
          }))} />
        {!isLoading && !error && activeRaces.length > 0 && <p className="calendar-season-total">{completedRacesCount} из {activeRaces.length} этапов завершено</p>}
      </div>

      {isLoading && <section className="calendar-loading" role="status" aria-label={`Загрузка календаря ${year}`}>
        <p>Загружаем календарь {year}…</p>
        <div aria-hidden="true"><span /><span /><span /></div>
      </section>}
      {error && !isLoading && <PageFeedback message={error} retry={() => void loadCalendar(year)} />}
      {!isLoading && !error && emptyMessage && <section className="calendar-empty" role="status">
        <h2>Расписание пока недоступно</h2><p>{emptyMessage} для сезона {year}.</p>
        <button type="button" className="calendar-secondary" onClick={() => void loadCalendar(year)}>Повторить загрузку</button>
      </section>}
      {!isLoading && !error && activeRaces.length > 0 && !visibleRaces.length && <section className="calendar-empty" role="status">
        <h2>{filter === 'past' ? 'Все гонки ещё впереди' : 'Сезон завершён'}</h2>
        <p>В сезоне {year} {filter === 'past' ? 'пока нет прошедших этапов' : 'не осталось предстоящих этапов'}.</p>
        <button type="button" className="calendar-secondary" onClick={() => setFilter('all')}>Показать весь сезон</button>
      </section>}

      {!isLoading && !error && !emptyMessage && selectedRace && <div className="calendar-layout">
        <section className="calendar-overview" id="calendar-overview" aria-labelledby="calendar-selected-name">
          <article className="calendar-selected" key={`${year}-${selectedRace.round}`}>
            <div className="calendar-race-scene race-flag-scene">
              <RaceFlagBackdrop country={selectedRace.country} eventName={selectedRace.event_name} />
              <div className="calendar-race-hero">
                <div className="calendar-race-copy">
                  <h2 id="calendar-selected-name" ref={selectedHeading} tabIndex={-1}>{selectedRace.event_name}</h2>
                  <p className="calendar-venue">{[selectedRace.location, selectedRace.country].filter(Boolean).filter((part, index, parts) => parts.indexOf(part) === index).join(', ')}</p>
                  <p className="calendar-round-status">Этап {selectedRace.round}<span className={`calendar-status calendar-status--${selectedStatus}`}>{calendarStatusLabel[selectedStatus ?? 'unknown']}</span></p>
                </div>
                <div className="calendar-track" aria-hidden="true">
                  <AnimatedTrackMap eventName={selectedRace.event_name} location={selectedRace.location} season={year}
                    className="calendar-track-map" svgClassName="calendar-track-svg" loadingClassName="calendar-track-loading" fitRoute animate={false} />
                </div>
              </div>
              <div className="calendar-race-start">
                <div><span>Гонка</span><strong>{selectedDateLabel}<span>{parseRaceTime(selectedRace.race_start_utc) !== null ? new Intl.DateTimeFormat('ru-RU', { timeZone: userTz, hour: '2-digit', minute: '2-digit' }).format(new Date(selectedRace.race_start_utc!)) : 'Время уточняется'}</span></strong><small>{timezoneName(userTz)}</small></div>
                <Link className="calendar-primary" to={`/next-race?season=${year}&round=${selectedRace.round}`}>Открыть уик-энд<CalendarChevron /></Link>
              </div>
            </div>
            {selectedRace.is_cancelled ? <p className="calendar-cancelled-note">Этап отменён. Указанные даты сохранены для справки.</p> : <details className="calendar-disclosure">
              <summary><span>Расписание сессий<small>{timezoneName(userTz)}</small></span><CalendarChevron /></summary>
              <dl className="calendar-sessions">
                {selectedSessions.map(session => <div key={session.key} className={session.key === 'race' ? 'calendar-session-race' : ''}>
                  <dt><GlossaryText>{session.label}</GlossaryText></dt>
                  <dd>{parseRaceTime(session.iso) === null ? 'Время уточняется' : <time dateTime={session.iso!}>{formatSessionTime(session.iso)}</time>}</dd>
                </div>)}
              </dl>
            </details>}
            {selectedResultLinks.length > 0 && <div className="calendar-results">
              <h3>Результаты сессий</h3>
              <div>{selectedResultLinks.map(link => <Link className="calendar-secondary" key={link.key} to={link.href}>{link.label}<CalendarChevron /></Link>)}</div>
            </div>}
            {isCompletedStatus(selectedStatus) && <details className="calendar-disclosure calendar-podium" onToggle={event => {
              if (event.currentTarget.open) void loadPodium(selectedRace.round);
            }}>
              <summary><span>Подиум гонки</span><CalendarChevron /></summary>
              {selectedPodium?.loading && <p role="status">Загружаем подиум…</p>}
              {!selectedPodium?.loading && selectedPodium?.error && <div className="calendar-podium-error" role="status"><p>{selectedPodium.error}</p><button type="button" className="calendar-secondary" onClick={() => void loadPodium(selectedRace.round)}>Повторить</button></div>}
              {!selectedPodium?.loading && Boolean(selectedPodium?.results.length) && <ol className="calendar-podium-list">
                {selectedPodium!.results.map(result => <li key={result.position}>
                  <span className="calendar-podium-place">{result.position}</span><span><strong>{result.name}</strong><small>{result.team || 'Команда не указана'}</small></span><span>{optionalNumber(result.points) ?? '—'} оч.</span>
                </li>)}
              </ol>}
            </details>}
          </article>
          {selectedInsights && <details className="calendar-disclosure calendar-circuit-facts" key={`facts-${year}-${selectedRace.round}`}>
            <summary><span>О трассе<small>{selectedRace.location}</small></span><CalendarChevron /></summary>
            <dl className="calendar-circuit-stats">{selectedInsights.stats.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
            <div className="calendar-facts">{selectedInsights.facts.map(fact => <div key={fact.title}><h3>{fact.title}</h3><p>{fact.text}</p></div>)}</div>
          </details>}
        </section>

        <section className="calendar-race-list" aria-labelledby="calendar-list-title">
          <div className="calendar-list-heading"><h2 id="calendar-list-title">{filterLabel}</h2><span>{visibleRaces.length}</span></div>
          <p className="calendar-list-help">Выберите этап, чтобы посмотреть расписание.</p>
          <ol className="calendar-stages">
            {visibleRaces.map(race => {
              const status = calendarState.statusByRound.get(race.round) || 'future';
              const date = raceDateParts(race, userTz);
              const selected = selectedRace.round === race.round;
              return <li key={race.round}>
                <button type="button" className={`calendar-stage race-flag-scene${selected ? ' is-selected' : ''}`}
                  aria-label={`Выбрать этап ${race.round}: ${race.event_name}`} aria-pressed={selected} aria-controls="calendar-overview" onClick={() => selectRace(race)}>
                  <RaceFlagBackdrop country={race.country} eventName={race.event_name} />
                  <span className="calendar-stage-date"><strong>{date.day}</strong><span>{date.month}</span></span>
                  <span className="calendar-stage-info"><span className="calendar-stage-meta">Этап {race.round}{race.sprint_start_utc && <span>Спринт</span>}</span><strong>{race.event_name.replace(/Grand Prix/gi, 'GP')}</strong><span className="calendar-stage-location">{race.location}</span><span className={`calendar-status calendar-status--${status}`}>{calendarStatusLabel[status]}</span></span>
                  <CalendarChevron />
                </button>
              </li>;
            })}
          </ol>
        </section>
      </div>}
    </div>
  );
}

function CalendarChevron() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>;
}

export default SeasonPage;
