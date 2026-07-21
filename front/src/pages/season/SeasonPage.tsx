import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
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
type RaceResultsResponse = { round?: number | null; results?: unknown[]; data_incomplete?: boolean };
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
  const [expandedRound, setExpandedRound] = useState<number | null>(null);
  const [desktopSelectedRound, setDesktopSelectedRound] = useState<number | null>(null);
  const [calendarNowMs, setCalendarNowMs] = useState(() => Date.now());
  const [latestReadyRound, setLatestReadyRound] = useState<number | null>(null);

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
    setExpandedRound(null);
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
                <button
                  key={`desktop-${race.round}`}
                  type="button"
                  className={`season-desktop-race-item ${statusClass} ${isSelected ? "active" : ""}`}
                  onClick={() => setDesktopSelectedRound(race.round)}
                  aria-pressed={isSelected}
                >
                  <div className="season-desktop-race-info">
                    <div className="season-desktop-race-topline">
                      <div className="race-round">
                        <span className="race-round-prefix">
                          Этап {String(race.round).padStart(2, "0")} •
                        </span>
                        <span className={`race-round-status ${statusClass}`}>{statusLabel}</span>
                      </div>
                      <span className="season-desktop-race-icon">{isSelected ? "➤" : statusClass === "live" ? "●" : isFinished ? "▣" : "○"}</span>
                    </div>
                    <div className="race-name">{timelineRaceName(race.event_name)}</div>
                    <div className="race-loc">{dateLabel} • {race.location}</div>
                  </div>
                </button>
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
            const isExpanded = expandedRound === race.round;
            const hasSprint = Boolean(race.sprint_start_utc);
            const hasSprintQuali = Boolean(race.sprint_quali_start_utc);
            return (
              <div key={race.round} className="season-race-item">
                <div
                  id={statusClass === "next" ? "next-race-card" : undefined}
                  className={`race-card ${statusClass}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/race-details?season=${year}&round=${race.round}`)}
                  onKeyDown={(e) =>
                    e.key === "Enter" && navigate(`/race-details?season=${year}&round=${race.round}`)
                  }
                >
                  <div className="race-date-box">
                    <span className="date-day">{day}</span>
                    <span className="date-month">{month}</span>
                  </div>
                  <div className="race-info">
                    <div className="race-round">Этап {race.round}</div>
                    <div className="race-name">{race.event_name}</div>
                    <div className="race-loc">📍 {race.location}</div>
                  </div>
                  <div className="race-status">{statusIcon}</div>
                  <button
                    type="button"
                    className="race-insights-toggle"
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpandedRound((prev) => (prev === race.round ? null : race.round));
                    }}
                  >
                    {isExpanded ? "Скрыть факты ▲" : "Факты ▼"}
                  </button>
                </div>

                {isExpanded && (
                  <div className="season-race-insights">
                    <div className="season-results-links">
                      <button
                        type="button"
                        className="season-result-link"
                        onClick={() => navigate(`/race-results?mode=archive&season=${year}&round=${race.round}`)}
                      >
                        🏁 Гонка
                      </button>
                      <button
                        type="button"
                        className="season-result-link"
                        onClick={() => navigate(`/quali-results?mode=archive&season=${year}&round=${race.round}`)}
                      >
                        ⏱ Квала
                      </button>
                      {hasSprint && (
                        <button
                          type="button"
                          className="season-result-link"
                          onClick={() => navigate(`/sprint-results?mode=archive&season=${year}&round=${race.round}`)}
                        >
                          ⚡🏁 Спринт
                        </button>
                      )}
                      {hasSprintQuali && (
                        <button
                          type="button"
                          className="season-result-link"
                          onClick={() => navigate(`/sprint-quali-results?mode=archive&season=${year}&round=${race.round}`)}
                        >
                          ⚡⏱ Спринт-квала
                        </button>
                      )}
                    </div>
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
                )}
              </div>
            );
          })}
      </div>
    </>
  );
}

export default SeasonPage;
