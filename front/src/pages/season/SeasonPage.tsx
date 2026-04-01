import { useState, useEffect, useCallback, useRef } from "react";
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
  const [desktopTrackSvg, setDesktopTrackSvg] = useState<string | null>(null);
  const desktopTrackRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    let cancelled = false;
    async function loadDesktopTrack() {
      if (!desktopRace?.event_name) {
        setDesktopTrackSvg(null);
        return;
      }
      try {
        const res = await fetch(`/static/circuit/${desktopRace.event_name}.svg`);
        if (!res.ok || cancelled) {
          setDesktopTrackSvg(null);
          return;
        }
        const text = await res.text();
        if (!cancelled) setDesktopTrackSvg(text);
      } catch {
        if (!cancelled) setDesktopTrackSvg(null);
      }
    }
    loadDesktopTrack();
    return () => {
      cancelled = true;
    };
  }, [desktopRace?.event_name]);

  useEffect(() => {
    if (!desktopTrackSvg || !desktopTrackRef.current) return;
    const container = desktopTrackRef.current;
    container.innerHTML = desktopTrackSvg;
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
    svg.getBoundingClientRect();
    setTimeout(() => {
      outlineGroup.querySelectorAll(".track-outline").forEach((p) => p.classList.add("animate"));
      fillGroup.querySelectorAll(".track-fill").forEach((p) => p.classList.add("animate"));
    }, 100);
  }, [desktopTrackSvg]);

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
          <div className="season-desktop-list">
            {races.map((race, index) => {
              const raceDate = new Date(race.date);
              const raceEndCheck = new Date(raceDate);
              raceEndCheck.setDate(raceEndCheck.getDate() + 1);
              const isNext = index === nextRaceIndex;
              const isCancelled = Boolean(race.is_cancelled);
              const isFinished = raceEndCheck < now;
              const statusClass = isCancelled ? "cancelled" : isFinished ? "finished" : isNext ? "next" : "future";
              const isSelected = desktopRace.round === race.round;
              const statusLabel = isCancelled
                ? "Отменен"
                : isSelected
                  ? "Выбрано"
                  : isNext
                    ? "Следующая"
                    : isFinished
                      ? "Завершен"
                      : "";
              const day = raceDate.toLocaleDateString("ru-RU", { timeZone: userTz, day: "numeric" });
              const month = raceDate
                .toLocaleDateString("ru-RU", { timeZone: userTz, month: "short" })
                .replace(".", "");
              return (
                <button
                  key={`desktop-${race.round}`}
                  type="button"
                  className={`season-desktop-race-item ${statusClass} ${isSelected ? "active" : ""}`}
                  onClick={() => setDesktopSelectedRound(race.round)}
                >
                  <div className="season-desktop-date-box">
                    <span className="date-day">{day}</span>
                    <span className="date-month">{month}</span>
                  </div>
                  <div className="season-desktop-race-info">
                    <div className="season-desktop-race-topline">
                      <div className="race-round">Round {race.round}</div>
                      {statusLabel && <span className={`season-desktop-status ${statusClass} ${isSelected ? "active" : ""}`}>{statusLabel}</span>}
                    </div>
                    <div className="race-name">{race.event_name}</div>
                    <div className="race-loc">📍 {race.location}</div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="season-desktop-details">
            <div className="season-desktop-toolbar">
              <div className="season-desktop-year-select">
                <YearSelect
                  value={year}
                  onChange={handleYearChange}
                  minYear={1950}
                  maxYear={currentRealYear}
                  placeholder="Введи год"
                />
              </div>
            </div>

            <div className="season-desktop-main-card">
              <div className="season-desktop-track-wrap">
                <div className="track-map-container season-desktop-track">
                  {!desktopTrackSvg && <div className="no-map-placeholder">🏁</div>}
                  <div
                    ref={desktopTrackRef}
                    style={{ width: "100%", height: "100%", display: desktopTrackSvg ? "block" : "none" }}
                  />
                </div>
              </div>
              <div className="season-desktop-title">{`ROUND ${desktopRace.round} | ${desktopRace.location}`}</div>
              <div className="season-desktop-subtitle">{desktopRace.event_name}</div>

              <div className="season-desktop-stats">
                {desktopInsights?.stats.slice(0, 4).map((item) => (
                  <div className="season-desktop-stat-box" key={item.label}>
                    <div className="season-desktop-stat-label">{item.label}</div>
                    <div className="season-desktop-stat-value">{item.value}</div>
                  </div>
                ))}
              </div>

              <div className="season-desktop-facts">
                {desktopInsights?.facts.slice(0, 3).map((fact) => (
                  <div key={fact.title} className="season-desktop-fact-item">
                    <div className="season-desktop-fact-title">{fact.title}</div>
                    <div className="season-desktop-fact-text">{fact.text}</div>
                  </div>
                ))}
              </div>

              <div className="season-desktop-links">
                <button
                  type="button"
                  className="season-result-link"
                  onClick={() => navigate(`/race-results?mode=archive&season=${year}&round=${desktopRace.round}`)}
                >
                  🏁 Гонка
                </button>
                <button
                  type="button"
                  className="season-result-link"
                  onClick={() => navigate(`/quali-results?mode=archive&season=${year}&round=${desktopRace.round}`)}
                >
                  ⏱ Квала
                </button>
                {desktopRace.sprint_start_utc && (
                  <button
                    type="button"
                    className="season-result-link"
                    onClick={() => navigate(`/sprint-results?mode=archive&season=${year}&round=${desktopRace.round}`)}
                  >
                    ⚡🏁 Спринт
                  </button>
                )}
                {desktopRace.sprint_quali_start_utc && (
                  <button
                    type="button"
                    className="season-result-link"
                    onClick={() => navigate(`/sprint-quali-results?mode=archive&season=${year}&round=${desktopRace.round}`)}
                  >
                    ⚡⏱ Спринт-квала
                  </button>
                )}
              </div>
            </div>
          </div>
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
