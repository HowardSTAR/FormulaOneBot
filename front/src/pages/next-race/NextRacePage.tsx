import { useState, useEffect } from "react";
import { BackButton } from "../../components/BackButton";
import { AnimatedTrackMap } from "../../components/AnimatedTrackMap";
import { apiRequest } from "../../helpers/api";
import { getDisplayTimezone } from "../../helpers/timezone";
import { getCircuitInsightsRu } from "../../assets/circuitInsightsRu";

type NextRaceResponse = {
  status: string;
  event_name?: string;
  is_cancelled?: boolean;
  country?: string;
  location?: string;
  season?: number;
  round?: number;
  date?: string;
};
type Session = { name: string; utc_iso?: string; utc?: string };
type ScheduleResponse = { sessions?: Session[] };
type SettingsResponse = { timezone?: string };

function NextRacePage() {
  const [title, setTitle] = useState("Загрузка...");
  const [location, setLocation] = useState("...");
  const [eventName, setEventName] = useState<string | null>(null);
  const [isCancelled, setIsCancelled] = useState(false);
  const [raceCountry, setRaceCountry] = useState("");
  const [raceCity, setRaceCity] = useState("");
  const [raceDateText, setRaceDateText] = useState("--");
  const [raceTimeText, setRaceTimeText] = useState("--:--");
  const [displayTimezone, setDisplayTimezone] = useState("Локальное время");
  const [raceRound, setRaceRound] = useState<number | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [expandedFactIndex, setExpandedFactIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [layoutPhase, setLayoutPhase] = useState<"draw" | "split">("draw");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [raceRes, settingsRes] = await Promise.allSettled([
          apiRequest<NextRaceResponse>("/api/next-race"),
          apiRequest<SettingsResponse>("/api/settings"),
        ]);
        const raceData = raceRes.status === "fulfilled" ? raceRes.value : { status: "error" };
        const settings = settingsRes.status === "fulfilled" ? settingsRes.value : { timezone: "UTC" };
        const userTz = getDisplayTimezone(settings?.timezone);

        if (cancelled) return;
        setDisplayTimezone(userTz.replace(/_/g, " "));
        if (raceData.status !== "ok") {
          setTitle(raceData.status === "season_finished" ? "Сезон завершен" : "Нет данных");
          setSessions([]);
          setLoading(false);
          return;
        }

        setTitle(raceData.event_name || "Загрузка...");
        setEventName(raceData.event_name || null);
        setIsCancelled(Boolean(raceData.is_cancelled));
        setRaceCountry(raceData.country || "");
        setRaceCity(raceData.location || "");
        setRaceRound(raceData.round ?? null);
        setLocation(`${raceData.country || ""}, ${raceData.location || ""}`);

        const scheduleData = await apiRequest<ScheduleResponse>("/api/weekend-schedule", {
          season: raceData.season!,
          round_number: raceData.round!,
        });
        if (cancelled) return;

        const raceSession =
          scheduleData.sessions?.find((s) => s.name === "Гонка" || s.name === "Race");
        if (raceSession?.utc_iso) {
          const dateObj = new Date(raceSession.utc_iso);
          setRaceDateText(
            dateObj.toLocaleDateString("ru-RU", {
              timeZone: userTz,
              day: "numeric",
              month: "long",
            }).toUpperCase()
          );
          setRaceTimeText(
            dateObj.toLocaleTimeString("ru-RU", {
              timeZone: userTz,
              hour: "2-digit",
              minute: "2-digit",
            })
          );
        } else {
          setRaceDateText(raceData.date || "TBA");
          setRaceTimeText("--:--");
        }

        if (scheduleData.sessions?.length) {
          setSessions(
            scheduleData.sessions.map((s) => {
              let time = "--:--";
              let date = "--.--";
              if (s.utc_iso) {
                try {
                  const d = new Date(s.utc_iso);
                  time = d.toLocaleTimeString("ru-RU", {
                    timeZone: userTz,
                    hour: "2-digit",
                    minute: "2-digit",
                  });
                  date = d.toLocaleDateString("ru-RU", {
                    timeZone: userTz,
                    day: "2-digit",
                    month: "2-digit",
                  });
                } catch {
                  time = s.utc || "--:--";
                }
              }
              return { ...s, _time: time, _date: date };
            })
          );
        } else {
          setSessions([]);
        }
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          const msg = e instanceof Error ? e.message : "Ошибка загрузки";
          setError(msg);
          setTitle(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (loading) return;
    const delay = eventName ? 3000 : 800;
    const t = setTimeout(() => setLayoutPhase("split"), delay);
    return () => clearTimeout(t);
  }, [eventName, loading]);

  useEffect(() => {
    setExpandedFactIndex(0);
  }, [eventName]);

  const insights = getCircuitInsightsRu({
    eventName: eventName || "",
    country: raceCountry,
    location: raceCity,
    sessionsCount: sessions.length,
  });

  const desktopSessions = sessions.map((s) => {
    const d = s.utc_iso ? new Date(s.utc_iso) : null;
    const day =
      d && !Number.isNaN(d.getTime())
        ? d.toLocaleDateString("ru-RU", { weekday: "long" }).toUpperCase()
        : "СЕССИЯ";
    const date =
      d && !Number.isNaN(d.getTime())
        ? d.toLocaleDateString("ru-RU", { month: "short", day: "numeric" }).toUpperCase()
        : "--";
    const time = "_time" in s ? (s as Session & { _time: string })._time : "--:--";
    return { ...s, _day: day, _dateLabel: date, _timeLabel: time };
  });

  return (
    <>
      <div className="next-race-mobile">
        <BackButton>← <span>Главное меню</span></BackButton>
        <h2>{title}</h2>
        <p style={{ marginBottom: 20, opacity: 0.7 }}>{location}</p>

        {(eventName || loading) && (
        <div className={`next-race-hero ${layoutPhase}`}>
          <div className="next-race-start-block">
            <div className="next-race-start-label">{isCancelled ? "СТАТУС ЭТАПА" : "СТАРТ ГОНКИ"}</div>
            <div className="next-race-date">{isCancelled ? "ОТМЕНЕН" : raceDateText}</div>
            <div className="next-race-time">{isCancelled ? "Организатор отменил проведение этапа" : raceTimeText}</div>
          </div>
          <div className="next-race-dash" aria-hidden />
          <div className="next-race-track-wrap">
            {eventName ? (
              <AnimatedTrackMap
                eventName={eventName}
                className="track-map-container next-race"
                svgClassName="next-race-mobile-track-svg"
                loadingClassName="next-race-track-loading"
              />
            ) : (
              !loading && <div className="no-map-placeholder">🏁</div>
            )}
          </div>
        </div>
        )}
        <h3 style={{ marginLeft: 4 }}>Расписание уикенда</h3>
        <div className="standings-list">
          {loading && (
            <div className="loading">
              <div className="spinner" />
              <div>Загружаем расписание...</div>
            </div>
          )}
          {!loading && sessions.length === 0 && !error && (
            <div style={{ padding: 20, textAlign: "center" }}>Нет расписания</div>
          )}
          {!loading &&
            sessions.length > 0 &&
            sessions.map((s, i) => (
              <div key={i} className="standings-item">
                <div className="standings-info">
                  <div className="standings-name" style={{ fontSize: 16 }}>
                    {s.name}
                  </div>
                  <div className="standings-code" style={{ color: "var(--text-secondary)", marginTop: 4 }}>
                    <span style={{ color: "var(--primary)", fontWeight: 700 }}>
                      {"_time" in s ? (s as Session & { _time: string; _date: string })._time : "--:--"}
                    </span>
                    <span style={{ margin: "0 6px", opacity: 0.3 }}>|</span>
                    {"_date" in s ? (s as Session & { _time: string; _date: string })._date : "--.--"}
                  </div>
                </div>
              </div>
            ))}
        </div>

        {!loading && eventName && (
          <>
            <section className="next-race-stage-data-section">
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
            </section>

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
                        <div className="circuit-fact-text">{fact.text}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>

      {!loading && (eventName || title) && (
        <section className="next-race-desktop">
          <div className="next-race-desktop-main">
            <header className="next-race-desktop-hero">
              <div className="next-race-desktop-left">
                <div className="next-race-desktop-round">
                  ЭТАП {String(raceRound || 0).padStart(2, "0")}
                </div>
                <h1>{(eventName || title).replace(/\s+Grand Prix$/i, "\nGrand Prix")}</h1>
                <div className="next-race-desktop-location">
                  <b>{raceCity || raceCountry}</b>
                  <span>{raceCountry || "Formula 1"}</span>
                </div>
                <div className="next-race-desktop-start">
                  <div>
                    <span>{isCancelled ? "Статус этапа" : "Дата гонки"}</span>
                    <strong>{isCancelled ? "Отменён" : raceDateText}</strong>
                  </div>
                  <div className="accent">
                    <span>{isCancelled ? "Решение организатора" : "Старт"}</span>
                    <strong>{isCancelled ? "—" : raceTimeText}</strong>
                  </div>
                </div>
              </div>
              <div className="next-race-desktop-track">
                <div
                  className={`next-race-desktop-track-panel ${eventName ? "track-panel-appear" : ""}`}
                >
                  <div className="next-race-desktop-track-caption">
                    <span>Схема трассы</span>
                    <b>{raceCity || eventName}</b>
                  </div>
                  {eventName ? (
                    <AnimatedTrackMap
                      eventName={eventName}
                      className="next-race-desktop-track-map"
                      svgClassName="next-race-desktop-track-svg"
                      loadingClassName="next-race-track-loading"
                    />
                  ) : (
                    <div className="no-map-placeholder">🏁</div>
                  )}
                </div>
              </div>
            </header>

            <div className="next-race-desktop-stats">
              {insights.stats.slice(0, 4).map((item) => (
                <article className="next-race-desktop-stat" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </article>
              ))}
            </div>

            <section className="next-race-desktop-schedule">
              <div className="next-race-desktop-schedule-head">
                <h2>Расписание</h2>
                <span>Время: {displayTimezone}</span>
              </div>
              <div className="next-race-desktop-schedule-grid">
                {desktopSessions.map((s, i) => (
                  <article key={`${s.name}-${i}`} className={i === desktopSessions.length - 1 ? "active" : ""}>
                    <u>{s._day}</u>
                    <h5>{s.name}</h5>
                    <div>
                      <b>{s._timeLabel}</b>
                      <small>{s._dateLabel}</small>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="next-race-desktop-facts">
              <article className="next-race-desktop-overview">
                <div>
                  <h3>Обзор трассы</h3>
                  <p>{insights.facts[0]?.text || "Подробности трассы появятся позже."}</p>
                </div>
              </article>
              <div className="next-race-desktop-facts-list">
                {insights.facts.slice(1, 4).map((fact) => (
                  <div key={fact.title} className="next-race-desktop-fact-item">
                    <div className="next-race-desktop-fact-head">
                      <h6>{fact.title}</h6>
                      <span>⌄</span>
                    </div>
                    <p>{fact.text}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </section>
      )}
    </>
  );
}

export default NextRacePage;
