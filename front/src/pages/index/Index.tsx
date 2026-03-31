import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useHeroData } from "../../context/HeroDataContext";
import { hasTelegramAuth } from "../../helpers/auth";
import "./styles.css";
import Hero from "./Hero";

export type { NextRaceResponse, SessionItem } from "../../context/HeroDataContext";

function IndexPage() {
  const { nextRace, schedule, userTz, loaded, load } = useHeroData();
  const isAuthenticated = hasTelegramAuth();
  const currentYear = new Date().getFullYear();
  const hasSprintSession = schedule.some((s) => {
    const n = (s.name || "").toLowerCase();
    return n.includes("спринт") || n.includes("sprint");
  });

  const sessionTimesMs = schedule
    .map((s) => (s.utc_iso ? new Date(s.utc_iso).getTime() : NaN))
    .filter((v) => !Number.isNaN(v));

  const isSprintWeekendActive =
    hasSprintSession &&
    sessionTimesMs.length > 0 &&
    Date.now() >= Math.min(...sessionTimesMs) - 6 * 60 * 60 * 1000 &&
    Date.now() <= Math.max(...sessionTimesMs) + 12 * 60 * 60 * 1000 &&
    nextRace?.status === "ok";

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

      <div className="index-layout">
        <div className="index-main-column">
          <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} />

          <div className="index-panel">
            <div className="section-title">Последний этап</div>
            <div className="results-grid">
              <Link to="/race-results" className="menu-item index-result-tile">
                <span className="menu-icon">🏁</span>
                <span className="menu-label index-card-title">Гонка</span>
                <span className="index-card-desc">Финиш, очки и позиции</span>
              </Link>
              <Link to="/quali-results" className="menu-item index-result-tile">
                <span className="menu-icon">⏱</span>
                <span className="menu-label index-card-title">Квала</span>
                <span className="index-card-desc">Борьба за поул</span>
              </Link>
              {isSprintWeekendActive && (
                <>
                  <Link to="/sprint-results" className="menu-item index-result-tile">
                    <span className="menu-icon">⚡🏁</span>
                    <span className="menu-label index-card-title">Спринт</span>
                    <span className="index-card-desc">Короткая гонка уик-энда</span>
                  </Link>
                  <Link to="/sprint-quali-results" className="menu-item index-result-tile">
                    <span className="menu-icon">⚡⏱</span>
                    <span className="menu-label index-card-title">Спринт-квала</span>
                    <span className="index-card-desc">Стартовая решетка спринта</span>
                  </Link>
                </>
              )}
            </div>
          </div>

        </div>

        <div className="index-side-column">
          <div className="index-panel">
            <div className="section-title" id="season-title">
              Сезон {currentYear}
            </div>

            <div className="menu-grid index-quick-grid">
              <Link to="/drivers" className="menu-item index-nav-card">
                <span className="menu-icon">👤</span>
                <span className="menu-label index-card-title">Пилоты</span>
                <span className="index-card-desc">Личный зачет и форма</span>
              </Link>
              <Link to="/constructors" className="menu-item index-nav-card">
                <span className="menu-icon">🏎️</span>
                <span className="menu-label index-card-title">Команды</span>
                <span className="index-card-desc">Кубок конструкторов</span>
              </Link>
              <Link to="/compare" className="menu-item index-nav-card">
                <span className="menu-icon">⚔️</span>
                <span className="menu-label index-card-title">Сравнение</span>
                <span className="index-card-desc">Очки, темп и дуэли</span>
              </Link>
              {isAuthenticated && (
                <Link to="/voting" className="menu-item index-nav-card">
                  <span className="menu-icon">🗳️</span>
                  <span className="menu-label index-card-title">Голосование</span>
                  <span className="index-card-desc">Оценки и итоги этапов</span>
                </Link>
              )}
              <Link to="/season" className="menu-item full-width index-wide-link">
                <div className="index-wide-link-left">
                  <span className="menu-icon">📅</span>
                  <div className="index-wide-link-text">
                    <span className="menu-label index-card-title">Календарь</span>
                    <span className="index-card-desc">Расписание и этапы сезона</span>
                  </div>
                </div>
                <span className="index-wide-link-arrow">➜</span>
              </Link>
            </div>
          </div>

          {isAuthenticated && (
            <div className="index-my-section index-panel">
              <div className="section-title">Моё</div>
              <Link to="/favorites" className="menu-item full-width index-wide-link index-favorites-link">
                <div className="index-wide-link-left">
                  <span className="menu-icon">⭐</span>
                  <div className="index-wide-link-text">
                    <span className="menu-label index-card-title">Избранное</span>
                    <span className="index-card-desc">Любимые пилоты и команды</span>
                  </div>
                </div>
                <span className="index-wide-link-arrow">➜</span>
              </Link>

              <Link to="/settings" className="menu-item full-width index-wide-link">
                <div className="index-wide-link-left">
                  <span className="menu-icon">⚙️</span>
                  <div className="index-wide-link-text">
                    <span className="menu-label index-card-title">Настройки</span>
                    <span className="index-card-desc">Часовой пояс и уведомления</span>
                  </div>
                </div>
                <span className="index-wide-link-arrow index-wide-link-arrow-muted">➜</span>
              </Link>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default IndexPage;
