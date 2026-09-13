import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GlossaryText } from "../../components/GlossaryText";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { getDisplayTimezone } from "../../helpers/timezone";
import { getCircuitInsightsRu } from "../../assets/circuitInsightsRu";
import { DetailedTrackMap } from "../../components/DetailedTrackMap";
import { AnimatedTrackMap } from "../../components/AnimatedTrackMap";

type Session = { name: string; utc_iso?: string; local?: string };
type RaceDetailsResponse = {
  event_name: string;
  location: string;
  country: string;
  event_format?: string;
  sessions: Session[];
};
type SettingsResponse = { timezone?: string };

function RaceDetailsPage() {
  const [searchParams] = useSearchParams();
  const season = searchParams.get("season");
  const round = searchParams.get("round");
  const [data, setData] = useState<RaceDetailsResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedFactIndex, setExpandedFactIndex] = useState(0);

  useEffect(() => {
    if (!season || !round) {
      setError("Не указан этап");
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const [raceData, settingsData] = await Promise.all([
          apiRequest<RaceDetailsResponse>("/api/race-details", { season, round }),
          apiRequest<SettingsResponse>("/api/settings"),
        ]);
        if (cancelled) return;
        setData(raceData);
        setSettings(settingsData);

      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError("Ошибка загрузки данных");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [season, round]);

  if (error || (!season && !round)) {
    return (
      <>
        <BackButton fallback="/season">← <span>Назад</span></BackButton>
        <div className="error">{error || "Не указан этап"}</div>
      </>
    );
  }

  if (loading || !data) {
    return (
      <>
        <BackButton fallback="/season">← <span>Назад</span></BackButton>
        <div className="loading full-width">Загрузка данных трассы...</div>
      </>
    );
  }

  const userTz = getDisplayTimezone(settings?.timezone);
  const now = new Date();
  const insights = getCircuitInsightsRu({
    eventName: data.event_name,
    country: data.country,
    location: data.location,
    eventFormat: data.event_format,
    sessionsCount: data.sessions.length,
  });
  const hasSprint = data.sessions.some((s) => {
    const n = (s.name || "").toLowerCase();
    return n.includes("спринт") || n.includes("sprint");
  });

  const sessionsHtml = data.sessions.map((session) => {
    const sessionDate = session.utc_iso
      ? new Date(session.utc_iso)
      : session.local
        ? new Date(session.local)
        : new Date();
    const isPast = sessionDate < now;
    const isActive = !isPast && sessionDate.getTime() - now.getTime() < 86400000;
    let timeStr = "--:--";
    let dateStr = "--";
    try {
      timeStr = sessionDate.toLocaleTimeString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: userTz,
      });
      dateStr = sessionDate.toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "long",
        timeZone: userTz,
      });
    } catch {
      timeStr = sessionDate.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
      dateStr = sessionDate.toLocaleDateString("ru-RU");
    }
    return (
      <div
        key={session.name}
        className={`session-row ${isActive ? "active" : ""}`}
        style={isPast ? { opacity: 0.5 } : undefined}
      >
        <div className="session-name">{session.name}</div>
        <div className="session-time">
          <div className="time-local">{timeStr}</div>
          <div className="time-date">{dateStr}</div>
        </div>
      </div>
    );
  });

  return (
    <>
      <BackButton fallback="/season">← <span>Назад</span></BackButton>
      <div className="circuit-header">
        <div className="circuit-title">{data.event_name}</div>
        <div className="circuit-subtitle">
          <span>📍 {data.location}, {data.country}</span>
        </div>
      </div>

      <DetailedTrackMap key={`${season}:${data.event_name}`} eventName={data.event_name} season={Number(season)} preview={
        <AnimatedTrackMap eventName={data.event_name} className="track-map-container race-details" svgClassName="race-details-track-svg" loadingClassName="circuit-data-pending" />
      } />

      <div className="schedule-card">{sessionsHtml}</div>

      <div className="schedule-card">
        <div className="schedule-title">Результаты этапа</div>
        <div className="race-details-results-links">
          <Link to={`/race-results?mode=archive&season=${season}&round=${round}`} className="race-details-result-link">
            🏁 Гонка
          </Link>
          <Link to={`/quali-results?mode=archive&season=${season}&round=${round}`} className="race-details-result-link">
            ⏱ Квала
          </Link>
          {hasSprint && (
            <>
              <Link to={`/sprint-results?mode=archive&season=${season}&round=${round}`} className="race-details-result-link">
                ⚡🏁 Спринт
              </Link>
              <Link to={`/sprint-quali-results?mode=archive&season=${season}&round=${round}`} className="race-details-result-link">
                ⚡⏱ Спринт-квала
              </Link>
            </>
          )}
        </div>
      </div>

      <div className="circuit-insights-card">
        <div className="circuit-insights-title">Данные по этапу</div>
        <div className="circuit-insights-stats">
          {insights.stats.map((item) => (
            <div className="circuit-stat-box" key={item.label}>
              <div className="circuit-stat-label">{item.label}</div>
              <div className="circuit-stat-value">{item.value}</div>
              {item.hint ? <div className="circuit-stat-hint">{item.hint}</div> : null}
            </div>
          ))}
        </div>
      </div>

      <div className="circuit-insights-card">
        <div className="circuit-insights-title">Интересные факты</div>
        <div className="circuit-facts-list">
          {insights.facts.map((fact, idx) => {
            const expanded = expandedFactIndex === idx;
            return (
              <div className="circuit-fact-item" key={fact.title}>
                <button
                  type="button"
                  className={`circuit-fact-header ${expanded ? "expanded" : ""}`}
                  onClick={() => setExpandedFactIndex(expanded ? -1 : idx)}
                >
                  <span className="circuit-fact-title">{fact.title}</span>
                  <span className="circuit-fact-chevron">{expanded ? "▲" : "▼"}</span>
                </button>
                <div className={`circuit-fact-body ${expanded ? "expanded" : ""}`}>
                  <div className="circuit-fact-text"><GlossaryText>{fact.text}</GlossaryText></div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

export default RaceDetailsPage;
