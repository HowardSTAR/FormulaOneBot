import { useState, useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiRequest } from "../../helpers/api";

type Session = { name: string; utc_iso?: string; local?: string };
type RaceDetailsResponse = {
  event_name: string;
  location: string;
  country: string;
  event_format?: string;
  sessions: Session[];
};
type SettingsResponse = { timezone?: string };

const formatMap: Record<string, string> = {
  conventional: "Классический уикенд",
  sprint: "Спринт",
  sprint_qualifying: "Спринт-квалификация",
  sprint_shootout: "Спринт-шутаут",
};

function RaceDetailsPage() {
  const [searchParams] = useSearchParams();
  const season = searchParams.get("season");
  const round = searchParams.get("round");
  const [data, setData] = useState<RaceDetailsResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trackSvg, setTrackSvg] = useState<string | null>(null);
  const trackContainerRef = useRef<HTMLDivElement>(null);

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
          apiRequest<RaceDetailsResponse>(`/api/race-details?season=${season}&round=${round}`),
          apiRequest<SettingsResponse>("/api/settings"),
        ]);
        if (cancelled) return;
        setData(raceData);
        setSettings(settingsData);

        const trackUrl = `/static/circuit/${raceData.event_name}.svg`;
        const res = await fetch(trackUrl);
        if (res.ok) {
          const text = await res.text();
          if (!cancelled) setTrackSvg(text);
        }
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

  if (error || (!season && !round)) {
    return (
      <>
        <Link to="/season" className="btn-back">
          ← <span>Назад</span>
        </Link>
        <div className="error">{error || "Не указан этап"}</div>
      </>
    );
  }

  if (loading || !data) {
    return (
      <>
        <Link to="/season" className="btn-back">
          ← <span>Назад</span>
        </Link>
        <div className="loading full-width">Загрузка данных трассы...</div>
      </>
    );
  }

  const userTz = settings?.timezone || "UTC";
  const now = new Date();

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
      <Link to="/season" className="btn-back">
        ← <span>Назад</span>
      </Link>
      <div className="circuit-header">
        <div className="circuit-title">{data.event_name}</div>
        <div className="circuit-subtitle">
          <span>📍 {data.location}, {data.country}</span>
        </div>
      </div>

      <div className="track-map-container race-details">
        {!trackSvg && !loading && <div className="no-map-placeholder">🏁</div>}
        <div ref={trackContainerRef} style={{ width: "100%", height: "100%", display: trackSvg ? "block" : "none" }} />
      </div>

      <div className="schedule-card">{sessionsHtml}</div>
    </>
  );
}

export default RaceDetailsPage;
