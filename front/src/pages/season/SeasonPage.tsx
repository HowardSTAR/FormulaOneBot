import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { YearSelect } from "../../components/YearSelect";
import { apiRequest } from "../../helpers/api";
import { getDisplayTimezone } from "../../helpers/timezone";
import { getCircuitInsightsRu } from "../../assets/circuitInsightsRu";

const currentRealYear = new Date().getFullYear();

type Race = {
  round: number;
  event_name: string;
  location: string;
  date: string;
  is_cancelled?: boolean;
  first_session_start_utc?: string | null;
  race_start_utc?: string | null;
  quali_start_utc?: string | null;
  sprint_start_utc?: string | null;
  sprint_quali_start_utc?: string | null;
};
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
  round?: number | null;
  results?: RaceResult[];
  data_incomplete?: boolean;
};
type PodiumState = {
  loading: boolean;
  error: string | null;
  results: RaceResult[];
};
type CalendarRaceStatus = "cancelled" | "live" | "recent" | "next" | "finished" | "future";

const RACE_RESULTS_MIN_AGE_MS = 2 * 60 * 60 * 1000;

function parseRaceTime(value?: string | null): number | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function weekendStartTime(race: Race): number {
  const candidates = [
    race.first_session_start_utc,
    race.sprint_quali_start_utc,
    race.quali_start_utc,
    race.sprint_start_utc,
    race.race_start_utc,
  ]
    .map(parseRaceTime)
    .filter((value): value is number => value !== null);
  if (candidates.length > 0) return Math.min(...candidates);
  return new Date(race.date).getTime();
}

function isCompletedStatus(status: CalendarRaceStatus): boolean {
  return status === "finished" || status === "recent";
}

function sessionHasStarted(value: string | null | undefined, nowMs: number, fallback = false): boolean {
  const sessionTime = parseRaceTime(value);
  return sessionTime === null ? fallback : sessionTime <= nowMs;
}

function SeasonTrackMap({ eventName }: { eventName: string }) {
  const [trackSvg, setTrackSvg] = useState<string | null>(null);
  const [trackError, setTrackError] = useState(false);
  const trackContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/static/circuit/${eventName}.svg`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Track map not found");
        const svg = await response.text();
        if (!cancelled) setTrackSvg(svg);
      })
      .catch(() => {
        if (!cancelled) setTrackError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [eventName]);

  useEffect(() => {
    const container = trackContainerRef.current;
    if (!trackSvg || !container) return;
    container.innerHTML = trackSvg;
    const svg = container.querySelector("svg");
    if (!svg) return;
    svg.style.width = "100%";
    svg.style.height = "100%";
    const paths = svg.querySelectorAll("path, polyline");
    const outlineGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const fillGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    outlineGroup.classList.add("track-outline-group");
    fillGroup.classList.add("track-fill-group");
    paths.forEach((path) => {
      const outlinePath = path.cloneNode(true) as SVGElement;
      outlinePath.removeAttribute("fill");
      outlinePath.classList.add("track-outline");
      const length = (outlinePath as SVGPathElement).getTotalLength?.() ?? 0;
      outlinePath.style.strokeDasharray = String(length);
      outlinePath.style.strokeDashoffset = String(length);
      outlineGroup.appendChild(outlinePath);
      path.classList.add("track-fill");
      fillGroup.appendChild(path);
    });
    svg.innerHTML = "";
    svg.appendChild(outlineGroup);
    svg.appendChild(fillGroup);
    const animationFrame = window.requestAnimationFrame(() => {
      outlineGroup.querySelectorAll(".track-outline").forEach((path) => path.classList.add("animate"));
      fillGroup.querySelectorAll(".track-fill").forEach((path) => path.classList.add("animate"));
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [trackSvg]);

  return (
    <div className="season-desktop-track-map">
      {!trackSvg && !trackError && <span className="season-track-loading">Загрузка схемы трассы…</span>}
      {trackError && <span className="season-track-loading">Схема трассы недоступна</span>}
      <div ref={trackContainerRef} className="season-desktop-track-svg" />
    </div>
  );
}

function SeasonPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const yearFromUrl = parseInt(searchParams.get("year") || "", 10);
  const [year, setYear] = useState(
    yearFromUrl && yearFromUrl >= 1950 && yearFromUrl <= currentRealYear ? yearFromUrl : currentRealYear
  );
  const [races, setRaces] = useState<Race[]>([]);
  const [userTz, setUserTz] = useState(getDisplayTimezone());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);
  const [expandedPodiumRound, setExpandedPodiumRound] = useState<number | null>(null);
  const [expandedFactsRound, setExpandedFactsRound] = useState<number | null>(null);
  const [desktopSelectedRound, setDesktopSelectedRound] = useState<number | null>(null);
  const [calendarNowMs, setCalendarNowMs] = useState(() => Date.now());
  const [latestReadyRound, setLatestReadyRound] = useState<number | null>(null);
  const [podiums, setPodiums] = useState<Record<number, PodiumState>>({});

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
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    try {
      const data = await apiRequest<SeasonResponse>("/api/season", { season });
      if (!data.races || data.races.length === 0) {
        setRaces([]);
        setEmptyMessage("Расписание не найдено");
        setDesktopSelectedRound(null);
      } else {
        const loadedRaces = data.races;
        setRaces(loadedRaces);
        const nowLocal = new Date();
        nowLocal.setHours(0, 0, 0, 0);
        const nextIdx = loadedRaces.findIndex((r) => {
          const raceEnd = new Date(r.date);
          raceEnd.setDate(raceEnd.getDate() + 1);
          return raceEnd >= nowLocal;
        });
        const initial = nextIdx >= 0 ? loadedRaces[nextIdx] : loadedRaces[0];
        setDesktopSelectedRound(initial?.round ?? null);
      }
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
      setRaces([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCalendar(year);
  }, [year, loadCalendar]);

  const updateYear = useCallback((y: number) => {
    setYear(y);
    setExpandedPodiumRound(null);
    setExpandedFactsRound(null);
    setPodiums({});
    setSearchParams(y === currentRealYear ? {} : { year: String(y) }, { replace: true });
  }, [setSearchParams]);

  useEffect(() => {
    if (year !== currentRealYear || races.length === 0) {
      setLatestReadyRound(null);
      return;
    }

    let cancelled = false;
    const refreshStatus = async () => {
      const nowMs = Date.now();
      setCalendarNowMs(nowMs);
      const latestRaceStarted = [...races]
        .reverse()
        .find((race) => {
          const raceStart = parseRaceTime(race.race_start_utc);
          return raceStart !== null && raceStart <= nowMs;
        });

      if (!latestRaceStarted) {
        if (!cancelled) setLatestReadyRound(null);
        return;
      }

      const raceStart = parseRaceTime(latestRaceStarted.race_start_utc);
      if (raceStart === null || nowMs - raceStart < RACE_RESULTS_MIN_AGE_MS) {
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
          (response.results?.length || 0) >= 10 &&
          !response.data_incomplete;
        setLatestReadyRound(ready ? latestRaceStarted.round : null);
      } catch {
        // Сохраняем прошлое подтверждённое состояние и повторяем проверку через минуту.
      }
    };

    void refreshStatus();
    const intervalId = window.setInterval(() => void refreshStatus(), 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [races, year]);

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

  const calendarState = useMemo(() => {
    const statusByRound = new Map<number, CalendarRaceStatus>();
    if (races.length === 0) return { statusByRound, nextRaceIndex: -1 };

    if (year !== currentRealYear) {
      races.forEach((race) => statusByRound.set(race.round, race.is_cancelled ? "cancelled" : "finished"));
      return { statusByRound, nextRaceIndex: -1 };
    }

    let latestStartedWeekendIndex = -1;
    races.forEach((race, index) => {
      if (weekendStartTime(race) <= calendarNowMs) latestStartedWeekendIndex = index;
    });
    const liveIndex =
      latestStartedWeekendIndex >= 0 &&
      !races[latestStartedWeekendIndex].is_cancelled &&
      latestReadyRound !== races[latestStartedWeekendIndex].round
        ? latestStartedWeekendIndex
        : -1;
    const recentIndex = liveIndex < 0
      ? races.findIndex((race) => race.round === latestReadyRound)
      : -1;
    const nextRaceIndex = liveIndex >= 0
      ? -1
      : races.findIndex((race) => weekendStartTime(race) > calendarNowMs && !race.is_cancelled);

    races.forEach((race, index) => {
      let status: CalendarRaceStatus;
      if (race.is_cancelled) status = "cancelled";
      else if (index === liveIndex) status = "live";
      else if (index === recentIndex) status = "recent";
      else if (index === nextRaceIndex) status = "next";
      else if (index < Math.max(liveIndex, recentIndex, nextRaceIndex)) status = "finished";
      else status = "future";
      statusByRound.set(race.round, status);
    });

    return { statusByRound, nextRaceIndex };
  }, [calendarNowMs, latestReadyRound, races, year]);

  const desktopRace = races.find((r) => r.round === desktopSelectedRound) || races[0] || null;
  const desktopRaceStatus = desktopRace ? calendarState.statusByRound.get(desktopRace.round) : undefined;
  const completedRacesCount = races.filter((race) => {
    const status = calendarState.statusByRound.get(race.round);
    return status === "finished" || status === "recent";
  }).length;
  const desktopInsights = desktopRace
    ? getCircuitInsightsRu({
        eventName: desktopRace.event_name,
        country: "",
        location: desktopRace.location,
      })
    : null;

  const selectedRaceDate = desktopRace ? new Date(desktopRace.date) : null;
  const selectedDateLabel = selectedRaceDate
    ? selectedRaceDate.toLocaleDateString("ru-RU", { timeZone: userTz, day: "2-digit", month: "short" }).replace(".", "").toUpperCase()
    : "—";
  const formatSessionTime = (iso?: string | null): string =>
    iso
      ? new Date(iso).toLocaleTimeString("ru-RU", {
          timeZone: userTz,
          hour: "2-digit",
          minute: "2-digit",
        })
      : "--:--";
  const desktopFactTitles = ["Локация", "Ключевой участок", "Непредсказуемость"];
  const timelineRaceName = (name: string): string => name.replace(/Grand Prix/gi, "GP");
  const loadPodium = useCallback(async (round: number) => {
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
      const results = (response.results || [])
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
    if (selectDesktopRace) setDesktopSelectedRound(race.round);
    if (!isCompletedStatus(status)) {
      setExpandedPodiumRound(null);
      return;
    }
    const shouldOpen = expandedPodiumRound !== race.round;
    setExpandedPodiumRound(shouldOpen ? race.round : null);
    if (shouldOpen) void loadPodium(race.round);
  }, [expandedPodiumRound, loadPodium]);

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
          <div className="season-podium-message">{state.error}</div>
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
                <span className="season-podium-points">{result.points} оч.</span>
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
      <div className="page-head-row season-page-head">
        <h2 className="page-head-title">Календарь</h2>
        <div className="page-head-controls">
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={1950}
            maxYear={currentRealYear}
            placeholder="Введи год"
          />
        </div>
      </div>

      {!loading && !error && !emptyMessage && races.length > 0 && desktopRace && (
        <div className="season-desktop-layout">
          <section className="season-desktop-primary">
            <div className="season-desktop-primary-head">
              <div>
                <h3 className="season-desktop-main-heading">Календарь</h3>
                <p className="season-desktop-main-subheading">
                  Сезон {year} · {races.length} этапа · {completedRacesCount} завершено
                </p>
              </div>
              <div className="season-desktop-season-picker">
                <span className="season-desktop-season-label">Выберите сезон</span>
                <select
                  className="season-desktop-season-select"
                  value={year}
                  onChange={(e) => handleYearChange(Number(e.target.value))}
                >
                  {Array.from({ length: currentRealYear - 1949 }, (_, i) => currentRealYear - i).map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <article className="season-desktop-main-card season-desktop-hero-card">
              <div className="season-desktop-hero-media">
                <SeasonTrackMap key={desktopRace.event_name} eventName={desktopRace.event_name} />
                <div className="season-desktop-hero-next">
                  {desktopRaceStatus === "live"
                    ? "LIVE"
                    : desktopRaceStatus === "recent"
                      ? "Только что прошёл"
                      : desktopRaceStatus === "next"
                        ? "Следующий этап"
                        : desktopRaceStatus === "finished"
                          ? "Прошедший этап"
                          : "Предстоящий этап"}: {String(desktopRace.round).padStart(2, "0")}
                </div>
                <h4>{desktopRace.event_name}</h4>
                <div className="season-desktop-hero-meta">
                  <span>{selectedDateLabel}</span>
                  <span>{desktopRace.location}</span>
                </div>
              </div>

              <div className="season-desktop-hero-schedule">
                <h5>Расписание сессий</h5>
                <div className="season-desktop-session-grid">
                  {desktopRace.sprint_quali_start_utc && (
                    <div className="season-desktop-session-item">
                      <span>Спринт-квалификация</span>
                      <b>{formatSessionTime(desktopRace.sprint_quali_start_utc)}</b>
                    </div>
                  )}
                  {desktopRace.sprint_start_utc && (
                    <div className="season-desktop-session-item">
                      <span>Спринт</span>
                      <b>{formatSessionTime(desktopRace.sprint_start_utc)}</b>
                    </div>
                  )}
                  <div className="season-desktop-session-item">
                    <span>Квалификация</span>
                    <b>{formatSessionTime(desktopRace.quali_start_utc)}</b>
                  </div>
                  <div className="season-desktop-session-item focus">
                    <span>Grand Prix</span>
                    <b>{selectedDateLabel}</b>
                  </div>
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
              {desktopInsights?.facts.slice(0, 3).map((fact, i) => (
                <div key={fact.title} className="season-desktop-fact-item">
                  <div className="season-desktop-fact-title">{desktopFactTitles[i] || fact.title}</div>
                  <div className="season-desktop-fact-text">"{fact.text}"</div>
                </div>
              ))}
            </div>
          </section>

          <aside className="season-desktop-list season-desktop-timeline">
            <h4 className="season-desktop-timeline-title">Все этапы сезона · {races.length}</h4>
            {races.map((race) => {
              const raceDate = new Date(race.date);
              const statusClass = calendarState.statusByRound.get(race.round) || "future";
              const isFinished = statusClass === "finished" || statusClass === "recent";
              const isSelected = desktopRace.round === race.round;
              const isExpanded = expandedPodiumRound === race.round && isFinished;
              const statusLabel = statusClass === "cancelled"
                ? "ОТМЕНЕН"
                : statusClass === "live"
                  ? "LIVE"
                  : statusClass === "recent"
                    ? "ТОЛЬКО ЧТО"
                    : statusClass === "finished"
                      ? "ЗАВЕРШЕН"
                      : statusClass === "next"
                        ? "NEXT · СКОРО"
                        : "ЭТАП";
              const dateLabel = raceDate
                .toLocaleDateString("ru-RU", {
                  timeZone: userTz,
                  day: "2-digit",
                  month: "short",
                })
                .replace(".", "")
                .toUpperCase();
              return (
                <div
                  key={`desktop-${race.round}`}
                  className={`season-desktop-stage-shell ${isExpanded ? "expanded" : ""}`}
                >
                  <button
                    type="button"
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
                          {isFinished ? (isExpanded ? "−" : "+") : statusClass === "live" ? "●" : "○"}
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
                      {(isExpanded || podiums[race.round]) && renderPodium(race)}
                    </div>
                  </div>
                </div>
              );
            })}
          </aside>
        </div>
      )}

      <div className="season-races-grid">
        {loading && <div className="loading full-width"><div className="spinner" /><div>Загрузка календаря...</div></div>}
        {error && <div className="page-error">{error}</div>}
        {!loading && emptyMessage && (
          <div className="empty-state season-empty-state">
            <div className="empty-icon">🔮</div>
            <div className="empty-title">{emptyMessage}</div>
          </div>
        )}
        {!loading && !error && !emptyMessage &&
          races.map((race) => {
            const raceDate = new Date(race.date);
            const statusClass = calendarState.statusByRound.get(race.round) || "future";
            const statusIcon = statusClass === "cancelled"
              ? "ОТМЕНЕН"
              : statusClass === "live"
                ? "LIVE"
                : statusClass === "recent"
                  ? "ТОЛЬКО ЧТО"
                  : statusClass === "finished"
                    ? "🏁"
                    : statusClass === "next"
                      ? "NEXT · СКОРО"
                      : "";
            const day = raceDate.toLocaleDateString("ru-RU", {
              timeZone: userTz,
              day: "numeric",
            });
            const month = raceDate
              .toLocaleDateString("ru-RU", { timeZone: userTz, month: "short" })
              .replace(".", "");
            const insights = getCircuitInsightsRu({
              eventName: race.event_name,
              country: "",
              location: race.location,
            });
            const areFactsExpanded = expandedFactsRound === race.round;
            const completedFallback = isCompletedStatus(statusClass);
            const resultLinks = [
              {
                key: "sprintQuali",
                label: "Спринт-квала",
                href: `/sprint-quali-results?mode=archive&season=${year}&round=${race.round}`,
                visible: Boolean(race.sprint_quali_start_utc)
                  && sessionHasStarted(race.sprint_quali_start_utc, calendarNowMs),
              },
              {
                key: "sprint",
                label: "Спринт",
                href: `/sprint-results?mode=archive&season=${year}&round=${race.round}`,
                visible: Boolean(race.sprint_start_utc)
                  && sessionHasStarted(race.sprint_start_utc, calendarNowMs),
              },
              {
                key: "quali",
                label: "Квалификация",
                href: `/quali-results?mode=archive&season=${year}&round=${race.round}`,
                visible: sessionHasStarted(race.quali_start_utc, calendarNowMs, completedFallback),
              },
              {
                key: "race",
                label: "Гонка",
                href: `/race-results?mode=archive&season=${year}&round=${race.round}`,
                visible: sessionHasStarted(race.race_start_utc, calendarNowMs, completedFallback),
              },
            ].filter((item) => item.visible);
            return (
              <div key={race.round} className="season-race-item">
                <div
                  id={statusClass === "next" ? "next-race-card" : undefined}
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
                    <span className="race-status">{statusIcon}</span>
                  </button>
                  <button
                    type="button"
                    className="race-insights-toggle"
                    onClick={() => toggleRaceFacts(race)}
                    aria-expanded={areFactsExpanded}
                    aria-controls={`season-mobile-facts-${race.round}`}
                  >
                    Факты
                    <span aria-hidden="true">{areFactsExpanded ? "−" : "+"}</span>
                  </button>
                </div>

                <div
                  id={`season-mobile-facts-${race.round}`}
                  className={`season-stage-expansion season-mobile-stage-expansion ${areFactsExpanded ? "open" : ""}`}
                  aria-hidden={!areFactsExpanded}
                >
                  <div className="season-stage-expansion-inner">
                    <div className="season-race-insights season-mobile-race-facts-panel">
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
