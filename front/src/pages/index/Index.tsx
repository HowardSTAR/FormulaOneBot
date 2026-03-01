import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useHeroData } from "../../context/HeroDataContext";
import { isTelegramWebApp } from "../../helpers/telegram";
import "./styles.css";
import Hero from "./Hero";

export type { NextRaceResponse, SessionItem } from "../../context/HeroDataContext";

function IndexPage() {
  const { nextRace, schedule, userTz, loaded, load } = useHeroData();
  const currentYear = new Date().getFullYear();
  const inTelegram = isTelegramWebApp();

  useEffect(() => {
    if (!loaded) load();
  }, [loaded, load]);

  return (
    <>
      <div className="header-wrapper">
        <h2 style={{ margin: 0 }}>
          <span style={{ color: "var(--primary)" }}>F1</span> Hub
        </h2>
      </div>

      <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} />

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
        <Link to="/voting" className="menu-item">
          <span className="menu-icon">🗳️</span>
          <span className="menu-label">Голосование</span>
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

      {inTelegram && (
        <>
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
      )}
    </>
  );
}

export default IndexPage;
