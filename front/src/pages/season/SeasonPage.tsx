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
      } else {
        setRaces(data.races);
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

  return (
    <>
      <BackButton>← <span>Главное меню</span></BackButton>
      <div className="page-head-row">
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
