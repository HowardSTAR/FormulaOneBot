import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import "./styles.css";
import Hero from "./Hero";

type NextRaceStatus = "ok" | "season_finished" | "error";

export type NextRaceResponse = {
  status?: NextRaceStatus;
  event_name?: string;
  season?: number;
  round?: number;
  date?: string;
  next_session_iso?: string;
  next_session_name?: string;
};

function IndexPage() {
    const [data, setData] = useState<NextRaceResponse | null>(null);

  const currentYear = new Date().getFullYear();

  // Загрузка данных при монтировании
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await apiRequest<NextRaceResponse>("/api/next-race");
        if (cancelled) return;

        if (data.status === "ok" && data.event_name) {
            setData(data);
        }
      } catch (e) {
        if (!cancelled) {
          console.error(e);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <div className="header-wrapper">
        <h2 style={{ margin: 0 }}>
          <span style={{ color: "var(--primary)" }}>F1</span> Hub
        </h2>
      </div>

      <Hero {...data} />

      <div className="section-title">Последний этап</div>
      <div className="results-grid">
        <Link to="/race-results" className="menu-item">
          <span className="menu-icon">🏁</span>
          <span className="menu-label">Гонка</span>
        </Link>
        <Link to="/quali-results" className="menu-item">
          <span className="menu-icon">⏱</span>
          <span className="menu-label">Квала</span>
        </Link>
      </div>

      <div className="section-title" id="season-title">
        Сезон {currentYear}
      </div>

      <div className="menu-grid">
        <Link to="/drivers" className="menu-item">
          <span className="menu-icon">👤</span>
          <span className="menu-label">Пилоты</span>
        </Link>
        <Link to="/constructors" className="menu-item">
          <span className="menu-icon">🏎️</span>
          <span className="menu-label">Команды</span>
        </Link>
        <Link to="/compare" className="menu-item">
          <span className="menu-icon">⚔️</span>
          <span className="menu-label">Сравнение</span>
        </Link>
        <Link
          to="/season"
          className="menu-item full-width"
          style={{
            flexDirection: "row",
            justifyContent: "space-between",
            padding: "16px 24px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="menu-icon">📅</span>
            <span className="menu-label">Календарь</span>
          </div>
          <span>➜</span>
        </Link>
      </div>

      <div className="section-title">Моё</div>
      <Link
        to="/favorites"
        className="menu-item full-width"
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          padding: "16px 24px",
          borderColor: "rgba(255, 215, 0, 0.3)",
          marginBottom: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span className="menu-icon">⭐</span>
          <span className="menu-label" style={{ color: "#ffd700" }}>
            Избранное
          </span>
        </div>
        <span style={{ color: "#ffd700" }}>➜</span>
      </Link>

      <Link
        to="/settings"
        className="menu-item full-width"
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          padding: "16px 24px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span className="menu-icon">⚙️</span>
          <span className="menu-label">Настройки</span>
        </div>
        <span style={{ opacity: 0.5 }}>➜</span>
      </Link>
    </>
  );
}

export default IndexPage;
