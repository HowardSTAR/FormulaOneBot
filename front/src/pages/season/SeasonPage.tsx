import { localDateTime, optionalNumber, timezoneName } from '../../helpers/presentation';
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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
import type { CalendarRace as Race, CalendarFilter, CalendarRaceStatus } from '../../helpers/seasonCalendar';
import './season-filters.css';

const currentRealYear = new Date().getFullYear();

type SeasonResponse = { races?: Race[] };
type SettingsResponse = { timezone?: string };
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
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const {year, round: selectedRound, filter} = readCalendarQuery(searchParams, currentRealYear);
  const calendarRequest = useRef(0);
  const [races, setRaces] = useState<Race[]>([]);
  const [loadedYear, setLoadedYear] = useState<number | null>(null);
  const [userTz, setUserTz] = useState(getDisplayTimezone());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);
  const [expandedPodiumRound, setExpandedPodiumRound] = useState<number | null>(null);
  const [expandedFactsRound, setExpandedFactsRound] = useState<number | null>(null);
  const [calendarNowMs, setCalendarNowMs] = useState(() => Date.now());
  const [latestReadyRound, setLatestReadyRound] = useState<number | null>(null);
  const [podiums, setPodiums] = useState<Record<number, PodiumState>>({});
  const activeRaces = loadedYear === year ? races : [];
  const isLoading = loading || loadedYear !== year;
  const setFilter = (value: CalendarFilter) => {
    setExpandedPodiumRound(null);
    setExpandedFactsRound(null);
    setSearchParams(previous => {
      const next = new URLSearchParams(previous); next.set('filter', value);
      if (!filteredCalendar(activeRaces, calendarState.statusByRound, value).some(race => race.round === selectedRound)) next.delete('round');
      return next;
    }, {replace: true});
  };

  useEffect(() => {
    let cancelled = false;
    apiRequest<SettingsResponse>("/api/settings")
      .then((s) => {
        if (!cancelled) setUserTz(getDisplayTimezone(s?.timezone));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const loadCalendar = useCallback(async (season: number) => {
    const request = ++calendarRequest.current;
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    setLatestReadyRound(null);
    setPodiums({});
    setExpandedPodiumRound(null);
    setExpandedFactsRound(null);
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
    setExpandedPodiumRound(null);
    setExpandedFactsRound(null);
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
  const desktopRace = selectedCalendarRace(visibleRaces, selectedRound, filter, calendarState.statusByRound);
  const desktopRaceStatus = desktopRace ? calendarState.statusByRound.get(desktopRace.round) : undefined;
  const completedRacesCount = filteredCalendar(activeRaces, calendarState.statusByRound, 'past').length;
  const upcomingRacesCount = filteredCalendar(activeRaces, calendarState.statusByRound, 'upcoming').length;
  const desktopInsights = desktopRace
    ? getCircuitInsightsRu({
        season: year,
        eventName: desktopRace.event_name,
        country: desktopRace.country ?? "",
        location: desktopRace.location,
        eventFormat: desktopRace.sprint_start_utc ? 'Со спринтом' : 'Стандартный',
        sessionsCount: raceSessions(desktopRace).filter(session => session.iso).length,
      })
    : null;

  const selectedDateLabel = desktopRace ? raceDateParts(desktopRace, userTz).label : '—';
  const selectedResultLinks = desktopRace ? calendarResultLinks(desktopRace, year, calendarNowMs, desktopRaceStatus) : [];
  const formatSessionTime = (iso?: string | null): string => localDateTime(iso, userTz);
  const timelineRaceName = (name: string): string => name.replace(/Grand Prix/gi, "GP");
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

  const toggleRaceExpansion = useCallback((
    race: Race,
    status: CalendarRaceStatus,
    selectDesktopRace = false,
  ) => {
    if (selectDesktopRace) setSearchParams(previous => {
      const next = new URLSearchParams(previous); next.set('round', String(race.round)); return next;
    }, {replace: true});
    if (!isCompletedStatus(status)) {
      setExpandedPodiumRound(null);
      return;
    }
    const shouldOpen = expandedPodiumRound !== race.round;
    setExpandedPodiumRound(shouldOpen ? race.round : null);
    if (shouldOpen) void loadPodium(race.round);
  }, [expandedPodiumRound, loadPodium, setSearchParams]);

  const toggleRaceFacts = useCallback((race: Race) => {
    const shouldOpen = expandedFactsRound !== race.round;
    setExpandedFactsRound(shouldOpen ? race.round : null);
  }, [expandedFactsRound]);

  const renderPodium = (race: Race) => {
    const state = podiums[race.round];
    return (
      <div className="season-podium-content">
        <div className="season-podium-head">
          <div>
            <span>Итоги гонки</span>
            <strong>Топ-3 пилота</strong>
          </div>
          <button
            type="button"
            className="season-podium-all-results"
            onClick={() => navigate(`/race-results?mode=archive&season=${year}&round=${race.round}`)}
          >
            Полные результаты
            <span aria-hidden="true">→</span>
          </button>
        </div>
        {state?.loading && (
          <div className="season-podium-loading" role="status">
            <span className="spinner" />
            Загружаем подиум…
          </div>
        )}
        {!state?.loading && state?.error && (
          <div className="season-podium-message" role="status">{state.error} <button type="button" className="season-retry" onClick={() => void loadPodium(race.round)}>Повторить</button></div>
        )}
        {!state?.loading && Boolean(state?.results.length) && (
          <ol className="season-podium-list">
            {state.results.map((result) => (
              <li key={`${race.round}-${result.position}-${result.code}`} className={`position-${result.position}`}>
                <span className="season-podium-position">{String(result.position).padStart(2, "0")}</span>
                <span className="season-podium-code">{result.code || "—"}</span>
                <span className="season-podium-driver">
                  <strong>{result.name}</strong>
                  <small>{result.team || "Команда не указана"}</small>
                </span>
                <span className="season-podium-points">{optionalNumber(result.points) ?? '—'} оч.</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    );
  };

  return (
    <>
      <BackButton>← <span>Главное меню</span></BackButton>
      <header className="page-head-row season-page-head">
        <div>
          <h1 className="page-head-title season-calendar-title">Календарь</h1>
          <p className="season-calendar-summary">Сезон {year}{!isLoading && !error && activeRaces.length > 0 ? ` · Этапов: ${activeRaces.length} · Прошедших: ${completedRacesCount}` : ''}</p>
        </div>
        <div className="page-head-controls">
          <span className="season-year-label">Сезон</span>
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={1950}
            maxYear={currentRealYear}
            ariaLabel="Сезон календаря"
          />
        </div>
      </header>

      <nav className="season-filters" aria-label="Фильтр календаря">
        <button type="button" aria-pressed={filter === 'upcoming'} onClick={() => setFilter('upcoming')}>Предстоящие{!isLoading && !error && <span className="season-filter-count">{upcomingRacesCount}</span>}</button>
        <button type="button" aria-pressed={filter === 'past'} onClick={() => setFilter('past')}>Прошедшие{!isLoading && !error && <span className="season-filter-count">{completedRacesCount}</span>}</button>
        <button type="button" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>Весь сезон{!isLoading && !error && <span className="season-filter-count">{activeRaces.length}</span>}</button>
      </nav>
      {!isLoading && !error && activeRaces.length > 0 && !visibleRaces.length && <section className="season-calendar-empty" role="status"><p>В сезоне {year} {filter === 'past' ? 'пока нет прошедших этапов' : 'не осталось предстоящих этапов'}.</p><button type="button" className="season-retry" onClick={() => setFilter('all')}>Показать весь сезон</button></section>}
      {error && !isLoading && <PageFeedback message={error} retry={() => void loadCalendar(year)} />}
      {isLoading && <div className="loading full-width" role="status"><div className="spinner" /><div>Загрузка календаря {year}…</div></div>}
      {!isLoading && !error && emptyMessage && <section className="season-calendar-empty" role="status"><p>{emptyMessage} для сезона {year}.</p><button type="button" className="season-retry" onClick={() => void loadCalendar(year)}>Повторить загрузку</button></section>}

      {!isLoading && !error && !emptyMessage && desktopRace && (
        <div className="season-desktop-layout">
          <section className="season-desktop-primary">
            <article className="season-desktop-main-card season-desktop-hero-card" aria-labelledby="season-selected-name">
              <div className="season-desktop-hero-media">
                <AnimatedTrackMap
                  key={desktopRace.event_name}
                  eventName={desktopRace.event_name}
                  location={desktopRace.location}
                  season={year}
                  className="season-desktop-track-map"
                  svgClassName="season-desktop-track-svg"
                  loadingClassName="season-track-loading"
                />
                <div className="season-desktop-hero-next">
                  {calendarStatusLabel[desktopRaceStatus ?? 'unknown']} · Этап {desktopRace.round}
                </div>
                <h2 id="season-selected-name">{desktopRace.event_name}</h2>
                <div className="season-desktop-hero-meta">
                  <span>{selectedDateLabel}</span>
                  <span>{desktopRace.location}</span>
                </div>
              </div>

              <div className="season-desktop-hero-schedule">
                <h3 className="season-schedule-title">Расписание сессий</h3><p className="ui-data-context">Время: {timezoneName(userTz)}</p>
                <div className="season-desktop-session-grid">
                  {raceSessions(desktopRace).map(session => <div key={session.key} className={`season-desktop-session-item ${session.key === 'race' ? 'focus' : ''}`}>
                    <span><GlossaryText>{session.label}</GlossaryText></span><b>{parseRaceTime(session.iso) === null ? 'Время уточняется' : formatSessionTime(session.iso)}</b>
                  </div>)}
                </div>
                <div className="season-selected-actions">
                  <Link className="season-calendar-action primary" to={`/race-details?season=${year}&round=${desktopRace.round}`}>Расписание и трасса →</Link>
                  {selectedResultLinks.map(link => <Link className="season-calendar-action" key={link.key} to={link.href}>Результаты: {link.label}</Link>)}
                </div>
                <div className="season-desktop-stats">
                  {desktopInsights?.stats.slice(0, 4).map((item) => (
                    <div className="season-desktop-stat-box" key={item.label}>
                      <div className="season-desktop-stat-label">{item.label}</div>
                      <div className="season-desktop-stat-value">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>

            </article>

            <div className="season-desktop-facts-grid">
              {desktopInsights?.facts.slice(0, 3).map((fact) => (
                <div key={fact.title} className="season-desktop-fact-item">
                  <div className="season-desktop-fact-title">{fact.title}</div>
                  <div className="season-desktop-fact-text">{fact.text}</div>
                </div>
              ))}
            </div>
          </section>

          <aside className="season-desktop-list season-desktop-timeline">
            <h2 className="season-desktop-timeline-title">{filter === 'upcoming' ? 'Предстоящие' : filter === 'past' ? 'Прошедшие' : 'Весь сезон'} · {visibleRaces.length}{filter !== 'all' ? ` из ${activeRaces.length}` : ''}</h2>
            <p className="season-calendar-list-help">Выберите этап, чтобы открыть расписание{filter !== 'upcoming' ? ' и подиум' : ''}.</p>
            {visibleRaces.map((race) => {
              const statusClass = calendarState.statusByRound.get(race.round) || "future";
              const isFinished = isCompletedStatus(statusClass);
              const isSelected = desktopRace.round === race.round;
              const isExpanded = expandedPodiumRound === race.round && isFinished;
              const statusLabel = calendarStatusLabel[statusClass];
              const dateLabel = raceDateParts(race, userTz).label;
              return (
                <div
                  key={`desktop-${race.round}`}
                  className={`season-desktop-stage-shell ${isExpanded ? "expanded" : ""}`}
                >
                  <button
                    type="button"
                    aria-label={`Выбрать этап ${race.round}: ${race.event_name}`}
                    className={`season-desktop-race-item ${statusClass} ${isSelected ? "active" : ""}`}
                    onClick={() => toggleRaceExpansion(race, statusClass, true)}
                    aria-pressed={isSelected}
                    aria-expanded={isFinished ? isExpanded : undefined}
                    aria-controls={isFinished ? `season-podium-${race.round}` : undefined}
                  >
                    <div className="season-desktop-race-info">
                      <div className="season-desktop-race-topline">
                        <div className="race-round">
                          <span className="race-round-prefix">
                            Этап {String(race.round).padStart(2, "0")} •
                          </span>
                          <span className={`race-round-status ${statusClass}`}>{statusLabel}</span>
                        </div>
                        <span className="season-desktop-race-icon" aria-hidden="true">
                          {isFinished ? (isExpanded ? "−" : "+") : isSelected ? "✓" : "→"}
                        </span>
                      </div>
                      <div className="race-name">{timelineRaceName(race.event_name)}</div>
                      <div className="race-loc">{dateLabel} • {race.location}</div>
                    </div>
                  </button>
                  <div
                    id={`season-podium-${race.round}`}
                    className={`season-stage-expansion ${isExpanded ? "open" : ""}`}
                    aria-hidden={!isExpanded}
                  >
                    <div className="season-stage-expansion-inner">
                      {isExpanded && renderPodium(race)}
                    </div>
                  </div>
                </div>
              );
            })}
          </aside>
        </div>
      )}

      <div className="season-races-grid">
        {!isLoading && !error && !emptyMessage &&
          visibleRaces.map((race) => {
            const statusClass = calendarState.statusByRound.get(race.round) || "future";
            const statusIcon = calendarStatusLabel[statusClass];
            const {day, month} = raceDateParts(race, userTz);
            const insights = getCircuitInsightsRu({
              season: year,
              eventName: race.event_name,
              country: race.country ?? "",
              location: race.location,
              eventFormat: race.sprint_start_utc ? 'Со спринтом' : 'Стандартный',
              sessionsCount: raceSessions(race).filter(session => session.iso).length,
            });
            const areFactsExpanded = expandedFactsRound === race.round;
            const resultLinks = calendarResultLinks(race, year, calendarNowMs, statusClass);
            return (
              <div key={race.round} className="season-race-item">
                <div
                  id={race.round === calendarState.nextRound ? "next-race-card" : undefined}
                  className={`race-card ${statusClass} ${areFactsExpanded ? "expanded" : ""}`}
                >
                  <button
                    type="button"
                    className="season-mobile-race-open"
                    onClick={() => navigate(`/race-details?season=${year}&round=${race.round}`)}
                    aria-label={`Открыть ${race.event_name}`}
                  >
                    <span className="race-date-box">
                      <span className="date-day">{day}</span>
                      <span className="date-month">{month}</span>
                    </span>
                    <span className="race-info">
                      <span className="race-round">Этап {race.round}</span>
                      <span className="race-name">{race.event_name}</span>
                      <span className="race-loc">📍 {race.location}</span>
                    </span>
                  </button>
                  <div className="season-mobile-card-actions">
                    <span className="race-status">{statusIcon}</span>
                    <button
                      type="button"
                      className="race-insights-toggle"
                      onClick={() => toggleRaceFacts(race)}
                      aria-expanded={areFactsExpanded}
                      aria-controls={`season-mobile-facts-${race.round}`}
                      aria-label={`${resultLinks.length ? 'Результаты и факты' : 'Факты'}: ${race.event_name}`}
                    >
                      {resultLinks.length ? 'Результаты и факты' : 'Факты'}
                      <span aria-hidden="true">{areFactsExpanded ? "−" : "+"}</span>
                    </button>
                  </div>
                  <div
                    id={`season-mobile-facts-${race.round}`}
                    className={`season-stage-expansion season-mobile-stage-expansion ${areFactsExpanded ? "open" : ""}`}
                    aria-hidden={!areFactsExpanded}
                  >
                    <div className="season-stage-expansion-inner">
                      {areFactsExpanded && <div className="season-race-insights season-mobile-race-facts-panel">
                        {resultLinks.length > 0 && (
                          <div className="season-mobile-results">
                            <div className="season-mobile-results-head">Результаты этапа</div>
                            <div className="season-mobile-results-links">
                              {resultLinks.map((item) => (
                                <Link key={item.key} to={item.href} className="season-mobile-result-link">
                                  {item.label}
                                  <span aria-hidden="true">→</span>
                                </Link>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="season-race-stats">
                          {insights.stats.map((item) => (
                            <div className="season-race-stat-box" key={`${race.round}-${item.label}`}>
                              <div className="season-race-stat-label">{item.label}</div>
                              <div className="season-race-stat-value">{item.value}</div>
                            </div>
                          ))}
                        </div>
                        <div className="season-race-facts">
                          {insights.facts.map((fact) => (
                            <div className="season-race-fact-item" key={`${race.round}-${fact.title}`}>
                              <div className="season-race-fact-title">{fact.title}</div>
                              <div className="season-race-fact-text">{fact.text}</div>
                            </div>
                          ))}
                        </div>
                      </div>}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
}

export default SeasonPage;
