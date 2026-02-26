import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";

const currentRealYear = new Date().getFullYear();

type Race = {
  round: number;
  event_name: string;
  location: string;
  date: string;
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
  const [yearInput, setYearInput] = useState(String(year));
  const [races, setRaces] = useState<Race[]>([]);
  const [userTz, setUserTz] = useState("UTC");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiRequest<SettingsResponse>("/api/settings")
      .then((s) => {
        if (!cancelled && s?.timezone) setUserTz(s.timezone);
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

  useEffect(() => {
    setYearInput(String(year));
  }, [year]);

  const updateYear = useCallback((y: number) => {
    setYear(y);
    setSearchParams(y === currentRealYear ? {} : { year: String(y) }, { replace: true });
  }, [setSearchParams]);

  useEffect(() => {
    if (year === currentRealYear && races.length > 0) {
      const nextId = document.getElementById("next-race-card");
      nextId?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [year, races]);

  const handleSearch = () => {
    const y = parseInt(yearInput, 10);
    if (!y) return;
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

  const goCurrentYear = () => {
    updateYear(currentRealYear);
    setYearInput(String(currentRealYear));
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
      <h2>Календарь</h2>

      <div className="search-container">
        <input
          type="number"
          id="year-input"
          className="search-input"
          placeholder="Введи год"
          inputMode="numeric"
          value={yearInput}
          onChange={(e) => setYearInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button type="button" className="search-btn" onClick={handleSearch}>
          🔍
        </button>
        <button type="button" className="current-year-btn" onClick={goCurrentYear}>
          {currentRealYear}
        </button>
      </div>

      <div className="standings-list">
        {loading && <div className="loading full-width">Загрузка календаря...</div>}
        {error && <div style={{ color: "red", textAlign: "center" }}>{error}</div>}
        {!loading && emptyMessage && (
          <div style={{ textAlign: "center", padding: "40px 20px" }}>
            <div style={{ fontSize: 40 }}>🔮</div>
            <div style={{ fontWeight: 600 }}>{emptyMessage}</div>
          </div>
        )}
        {!loading && !error && !emptyMessage &&
          races.map((race, index) => {
            const raceDate = new Date(race.date);
            const raceEndCheck = new Date(raceDate);
            raceEndCheck.setDate(raceEndCheck.getDate() + 1);
            const isNext = index === nextRaceIndex;
            const isFinished = raceEndCheck < now;
            const statusClass: "finished" | "next" | "future" = isFinished
              ? "finished"
              : isNext
                ? "next"
                : "future";
            const statusIcon = isFinished ? "🏁" : isNext ? "NEXT" : "";
            const day = raceDate.toLocaleDateString("ru-RU", {
              timeZone: userTz,
              day: "numeric",
            });
            const month = raceDate
              .toLocaleDateString("ru-RU", { timeZone: userTz, month: "short" })
              .replace(".", "");
            return (
              <div
                key={race.round}
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
              </div>
            );
          })}
      </div>
    </>
  );
}

export default SeasonPage;
