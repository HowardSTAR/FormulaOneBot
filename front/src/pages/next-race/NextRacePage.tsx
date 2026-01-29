import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";

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
  const [raceDateText, setRaceDateText] = useState("--");
  const [raceTimeText, setRaceTimeText] = useState("--:--");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

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
          setError(true);
          setTitle("Ошибка загрузки");
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

  return (
    <>
      <Link to="/" className="btn-back">
        ← <span>Главное меню</span>
      </Link>
      <h2>{title}</h2>
      <p style={{ marginBottom: 20, opacity: 0.7 }}>{location}</p>

      <div className="card">
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 8 }}>СТАРТ ГОНКИ</div>
          <div id="race-time-local" style={{ fontSize: 24, fontWeight: 800, color: "var(--primary)", whiteSpace: "nowrap", textTransform: "uppercase" }}>
            {raceDateText}
          </div>
          <div id="race-date" style={{ fontSize: 16, marginTop: 4 }}>{raceTimeText}</div>
        </div>
      </div>

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
    </>
  );
}

export default NextRacePage;
