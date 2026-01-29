import { useState, useEffect } from "react";
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
        const data = await apiRequest<NextRaceResponse>("http://localhost:8000/api/next-race");
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
        <a href="race-results.html" className="menu-item">
          <span className="menu-icon">🏁</span>
          <span className="menu-label">Гонка</span>
        </a>
        <a href="quali-results.html" className="menu-item">
          <span className="menu-icon">⏱</span>
          <span className="menu-label">Квала</span>
        </a>
      </div>

      <div className="section-title" id="season-title">
        Сезон {currentYear}
      </div>

      <div className="menu-grid">
        <a href="drivers.html" className="menu-item">
          <span className="menu-icon">👤</span>
          <span className="menu-label">Пилоты</span>
        </a>
        <a href="constructors.html" className="menu-item">
          <span className="menu-icon">🏎️</span>
          <span className="menu-label">Команды</span>
        </a>
        <a href="compare.html" className="menu-item">
          <span className="menu-icon">⚔️</span>
          <span className="menu-label">Сравнение</span>
        </a>
        <a
          href="season.html"
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
        </a>
      </div>

      <div className="section-title">Моё</div>
      <a
        href="favorites.html"
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
      </a>

      <a
        href="settings.html"
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
      </a>
    </>
  );
}

export default IndexPage;
