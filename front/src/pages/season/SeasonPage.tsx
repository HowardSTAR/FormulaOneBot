import { useState, useEffect, useCallback } from "react";
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
  quali_start_utc?: string | null;
  sprint_start_utc?: string | null;
  sprint_quali_start_utc?: string | null;
};
type SeasonResponse = { races?: Race[] };
type SettingsResponse = { timezone?: string };

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
    if (year === currentRealYear && races.length > 0) {
      const nextId = document.getElementById("next-race-card");
      nextId?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [year, races]);

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

  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const nextRaceIndex = races.findIndex((r) => {
    const raceEnd = new Date(r.date);
    raceEnd.setDate(raceEnd.getDate() + 1);
    return raceEnd >= now;
  });
  const desktopRace = races.find((r) => r.round === desktopSelectedRound) || races[0] || null;
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
  const desktopFactTitles = ["Location", "Setup Key", "Unpredictability"];
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
                <p className="season-desktop-main-subheading">Formula 1 World Championship</p>
              </div>
              <div className="season-desktop-season-picker">
                <span className="season-desktop-season-label">Select Season</span>
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
                <div className="season-desktop-hero-next">Next Round: {String(desktopRace.round).padStart(2, "0")}</div>
                <h4>{desktopRace.event_name}</h4>
                <div className="season-desktop-hero-meta">
                  <span>{selectedDateLabel}</span>
                  <span>{desktopRace.location}</span>
                </div>
              </div>

              <div className="season-desktop-hero-schedule">
                <h5>Session Schedule</h5>
                <div className="season-desktop-session-grid">
                  <div className="season-desktop-session-item">
                    <span>Sprint Quali</span>
                    <b>{formatSessionTime(desktopRace.sprint_quali_start_utc)}</b>
                  </div>
                  <div className="season-desktop-session-item">
                    <span>Sprint</span>
                    <b>{formatSessionTime(desktopRace.sprint_start_utc)}</b>
                  </div>
                  <div className="season-desktop-session-item">
                    <span>Qualifying</span>
                    <b>--:--</b>
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
            <h4 className="season-desktop-timeline-title">Season Timeline</h4>
            {races.map((race, index) => {
              const raceDate = new Date(race.date);
              const raceEndCheck = new Date(raceDate);
              raceEndCheck.setDate(raceEndCheck.getDate() + 1);
              const isNext = index === nextRaceIndex;
              const isCancelled = Boolean(race.is_cancelled);
              const isFinished = raceEndCheck < now;
              const statusClass = isCancelled ? "cancelled" : isFinished ? "finished" : isNext ? "next" : "future";
              const isSelected = desktopRace.round === race.round;
              const statusLabel = isCancelled ? "CANCELLED" : isFinished ? "FINISHED" : isNext ? "UPCOMING" : "ROUND";
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
                >
                  <div className="season-desktop-race-info">
                    <div className="season-desktop-race-topline">
                      <div className="race-round">Round {String(race.round).padStart(2, "0")} • {statusLabel}</div>
                      <span className="season-desktop-race-icon">{isSelected ? "➤" : isFinished ? "▣" : "○"}</span>
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
          races.map((race, index) => {
            const raceDate = new Date(race.date);
            const raceEndCheck = new Date(raceDate);
            raceEndCheck.setDate(raceEndCheck.getDate() + 1);
            const isNext = index === nextRaceIndex;
            const isCancelled = Boolean(race.is_cancelled);
            const isFinished = raceEndCheck < now;
            const statusClass: "finished" | "next" | "future" | "cancelled" = isCancelled
              ? "cancelled"
              : isFinished
                ? "finished"
                : isNext
                  ? "next"
                  : "future";
            const statusIcon = isCancelled ? "ОТМЕНЕН" : isFinished ? "🏁" : isNext ? "NEXT" : "";
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
                    <div className="race-round">Round {race.round}</div>
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
