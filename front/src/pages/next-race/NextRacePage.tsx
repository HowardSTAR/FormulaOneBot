import { useState, useEffect, useRef } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { getCircuitInsightsRu } from "../../data/circuitInsightsRu";

type NextRaceResponse = {
  status: string;
  event_name?: string;
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
  const [raceCountry, setRaceCountry] = useState("");
  const [raceCity, setRaceCity] = useState("");
  const [raceDateText, setRaceDateText] = useState("--");
  const [raceTimeText, setRaceTimeText] = useState("--:--");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [expandedFactIndex, setExpandedFactIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trackSvg, setTrackSvg] = useState<string | null>(null);
  const [layoutPhase, setLayoutPhase] = useState<"draw" | "split">("draw");
  const trackContainerRef = useRef<HTMLDivElement>(null);

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
        const userTz = settings?.timezone || "UTC";

        if (cancelled) return;
        if (raceData.status !== "ok") {
          setTitle(raceData.status === "season_finished" ? "Сезон завершен" : "Нет данных");
          setSessions([]);
          setLoading(false);
          return;
        }

        setTitle(raceData.event_name || "Загрузка...");
        setEventName(raceData.event_name || null);
        setRaceCountry(raceData.country || "");
        setRaceCity(raceData.location || "");
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
    if (!eventName || loading) return;
    let cancelled = false;
    async function loadTrack() {
      try {
        const trackUrl = `/static/circuit/${eventName}.svg`;
        const res = await fetch(trackUrl);
        if (res.ok && !cancelled) {
          const text = await res.text();
          setTrackSvg(text);
        }
      } catch {
        // ignore
      }
    }
    loadTrack();
    return () => { cancelled = true; };
  }, [eventName, loading]);

  useEffect(() => {
    if (!trackSvg || !trackContainerRef.current) return;
    const container = trackContainerRef.current;
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
    svg.getBoundingClientRect();
    setTimeout(() => {
      outlineGroup.querySelectorAll(".track-outline").forEach((p) => p.classList.add("animate"));
      fillGroup.querySelectorAll(".track-fill").forEach((p) => p.classList.add("animate"));
    }, 100);
  }, [trackSvg]);

  useEffect(() => {
    if (loading) return;
    const delay = trackSvg ? 4200 : 800;
    const t = setTimeout(() => setLayoutPhase("split"), delay);
    return () => clearTimeout(t);
  }, [trackSvg, loading]);

  useEffect(() => {
    setExpandedFactIndex(0);
  }, [eventName]);

  const insights = getCircuitInsightsRu({
    eventName: eventName || "",
    country: raceCountry,
    location: raceCity,
    sessionsCount: sessions.length,
  });

  return (
    <>
      <BackButton>← <span>Главное меню</span></BackButton>
      <h2>{title}</h2>
      <p style={{ marginBottom: 20, opacity: 0.7 }}>{location}</p>

      {(eventName || loading) && (
      <div className={`next-race-hero ${layoutPhase}`}>
        <div className="next-race-start-block">
          <div className="next-race-start-label">СТАРТ ГОНКИ</div>
          <div className="next-race-date">{raceDateText}</div>
          <div className="next-race-time">{raceTimeText}</div>
        </div>
        <div className="next-race-dash" aria-hidden />
        <div className="next-race-track-wrap">
          <div className="track-map-container next-race">
            {!trackSvg && !loading && <div className="no-map-placeholder">🏁</div>}
            <div
              ref={trackContainerRef}
              style={{ width: "100%", height: "100%", display: trackSvg ? "block" : "none" }}
            />
          </div>
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
                      <div className="circuit-fact-text">{fact.text}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </>
  );
}

export default NextRacePage;
