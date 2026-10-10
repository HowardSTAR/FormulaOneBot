import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useHeroData } from "../../context/useHeroData";
import { useAuthState } from "../../helpers/auth";
import { apiAssetUrl, apiRequest } from "../../helpers/api";
import { useMediaQuery } from '../../helpers/useMediaQuery';
import { getCountryFlagUrl } from "../../constants/flags";
import "./styles.css";
import Hero from "./Hero";
import IndexIcon from "./IndexIcon";
import { WeekendBoard, QuickAccess } from './WeekendBoard';
import { PersonalHome } from './PersonalHome';

export type { NextRaceResponse, SessionItem } from "../../context/HeroDataContext";

type DriverStanding = {
  position: number;
  name: string;
  points: number;
  code?: string;
  constructorId?: string;
  constructorName?: string;
};
type ConstructorStanding = {
  position: number;
  name: string;
  points: number;
  constructorId?: string;
};
type DriversResponse = { drivers?: DriverStanding[] };
type ConstructorsResponse = { constructors?: ConstructorStanding[] };
function teamLogoUrl(teamId: string, teamName: string, season: number): string {
  const team = teamId || teamName;
  return apiAssetUrl("/api/team-logo", { team, name: teamName, season });
}

const DRIVER_FLAG_BY_CODE: Record<string, string> = {
  VER: "nl",
  TSU: "jp",
  NOR: "gb",
  PIA: "au",
  LEC: "mc",
  HAM: "gb",
  RUS: "gb",
  ANT: "it",
  ALO: "es",
  STR: "ca",
  GAS: "fr",
  OCO: "fr",
  ALB: "th",
  SAI: "es",
  HUL: "de",
  BOR: "br",
  BEA: "gb",
  LAW: "nz",
};

const TEAM_FLAG_BY_ID: Record<string, string> = {
  mclaren: "gb",
  ferrari: "it",
  mercedes: "de",
  red_bull: "at",
  redbull: "at",
  alpine: "fr",
  aston_martin: "gb",
  rb: "it",
  "rb_f1_team": "it",
  williams: "gb",
  sauber: "ch",
  audi: "de",
  haas: "us",
  "haas_f1_team": "us",
  cadillac: "us",
};


function IndexArrow() {
  return <svg className="index-link-arrow" viewBox="0 0 24 24" aria-hidden><path d="m9 5 7 7-7 7" /></svg>;
}

function IndexPage() {
  const { nextRace, schedule, userTz, loaded, load } = useHeroData();
  const desktop = useMediaQuery('(min-width: 900px)');
  const auth = useAuthState();
  const currentYear = new Date().getFullYear();
  const widgetSeason = nextRace?.season || currentYear;
  const [totalRounds, setTotalRounds] = useState(0);
  const [driversTop, setDriversTop] = useState<DriverStanding[]>([]);
  const [constructorsTop, setConstructorsTop] = useState<ConstructorStanding[]>([]);
  const displayTz = userTz;
  useEffect(() => {
    if (!loaded) load();
  }, [loaded, load]);

  useEffect(() => {
    let cancelled = false;
    const season = widgetSeason;
    const loadStandings = async () => {
      try {
        const [driversRes, constructorsRes, calendarRes] = await Promise.allSettled([
          apiRequest<DriversResponse>("/api/drivers", { season }),
          apiRequest<ConstructorsResponse>("/api/constructors", { season }),
          apiRequest<{races: unknown[]}>("/api/season", { season }),
        ]);
        if (cancelled) return;
        setTotalRounds(calendarRes.status === "fulfilled" ? calendarRes.value.races.length : 0);
        setDriversTop(
          driversRes.status === "fulfilled" ? (driversRes.value.drivers || []).slice(0, 10) : []
        );
        setConstructorsTop(
          constructorsRes.status === "fulfilled" ? (constructorsRes.value.constructors || []).slice(0, 10) : []
        );
      } catch {
        if (cancelled) return;
        setDriversTop([]);
        setConstructorsTop([]);
      }
    };
    loadStandings();
    return () => {
      cancelled = true;
    };
  }, [widgetSeason]);

  return (
    <>
      {desktop ? <div className="index-desktop-shell index-dashboard">
        <section className="index-dashboard-top">
          <div className="index-hero-wrap index-desktop-hero-wrap">
            <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} showTrackMap />
            <PersonalHome auth={auth} timezone={displayTz} />
          </div>

          <WeekendBoard race={nextRace} sessions={schedule} timezone={displayTz} total={totalRounds} loaded={loaded} />
        </section>

        <section className="index-dashboard-main">
          <div className="index-standings-preview">
            <div className="index-dashboard-section-head index-standings-preview-head">
              <div>
                <span>Чемпионат {widgetSeason}</span>
                <h2>Положение после этапа</h2>
              </div>
            </div>

            <div className="index-standings-preview-grid">
              <Link to="/drivers" className="index-standing-column">
                <div className="index-standing-column-head"><strong>Пилоты</strong><span>Очки</span></div>
                {driversTop.slice(0, 5).map((driver) => (
                  <div className="index-standing-line" key={`${driver.position}-${driver.name}`}>
                    <b>{driver.position}</b>
                    <div>
                      {DRIVER_FLAG_BY_CODE[(driver.code || "").toUpperCase()] && (
                        <img src={getCountryFlagUrl(DRIVER_FLAG_BY_CODE[(driver.code || "").toUpperCase()])} alt="" />
                      )}
                      <span>{driver.name}</span>
                      <small>{driver.constructorName}</small>
                    </div>
                    <strong>{driver.points}</strong>
                  </div>
                ))}
                {driversTop.length === 0 && <span className="index-standing-loading">Загрузка зачёта…</span>}
                <span className="index-standing-more">Полная таблица <b aria-hidden>→</b></span>
              </Link>

              <Link to="/constructors" className="index-standing-column">
                <div className="index-standing-column-head"><strong>Команды</strong><span>Очки</span></div>
                {constructorsTop.slice(0, 5).map((team) => (
                  <div className="index-standing-line" key={`${team.position}-${team.name}`}>
                    <b>{team.position}</b>
                    <div>
                      <img
                        src={teamLogoUrl(team.constructorId || "", team.name, widgetSeason)}
                        alt=""
                        onError={(event) => { event.currentTarget.style.display = "none"; }}
                      />
                      <span>{team.name}</span>
                    </div>
                    <strong>{team.points}</strong>
                  </div>
                ))}
                {constructorsTop.length === 0 && <span className="index-standing-loading">Загрузка зачёта…</span>}
                <span className="index-standing-more">Полная таблица <b aria-hidden>→</b></span>
              </Link>
            </div>
          </div>

          <QuickAccess season={widgetSeason} />
        </section>
      </div>

      : <div className="index-mobile-stack">
      <div className="index-layout">
        <div className="index-hero-wrap">
          <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} />
          <PersonalHome auth={auth} timezone={displayTz} />
        </div>

        <WeekendBoard race={nextRace} sessions={schedule} timezone={displayTz} total={totalRounds} loaded={loaded} />
        <QuickAccess season={widgetSeason} />

        <div className="index-panel index-games-panel">
          <div className="section-title">Игры</div>
          <div className="games-list">
            <Link to="/reaction-game" className="menu-item games-item">
              <div className="index-wide-link-left">
                <IndexIcon name="reaction" />
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Тест реакции</span>
                  <span className="index-card-desc">Случайный старт светофора</span>
                </div>
              </div>
              <IndexArrow />
            </Link>
            <Link to="/reflex-grid-game" className="menu-item games-item">
              <div className="index-wide-link-left">
                <IndexIcon name="grid" />
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Reflex Grid</span>
                  <span className="index-card-desc">Скорость и точность на сетке</span>
                </div>
              </div>
              <IndexArrow />
            </Link>
            <Link to="/race-game" className="menu-item games-item">
              <div className="index-wide-link-left">
                <IndexIcon name="arcade" />
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Emerald Loop</span>
                  <span className="index-card-desc">Пиксельная гонка на три круга</span>
                </div>
              </div>
              <IndexArrow />
            </Link>
          </div>
        </div>

        <div className="index-my-section index-panel">
            <div className="section-title">Мой профиль</div>
            <Link to="/notifications" className="menu-item full-width index-wide-link">
              <div className="index-wide-link-left"><IndexIcon name="notifications" /><div className="index-wide-link-text">
                <span className="menu-label index-card-title">Уведомления</span>
                <span className="index-card-desc">История событий и push</span>
              </div></div><IndexArrow />
            </Link>
            <Link to="/favorites" className="menu-item full-width index-wide-link index-favorites-link">
              <div className="index-wide-link-left">
                <IndexIcon name="favorite" />
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Избранное</span>
                  <span className="index-card-desc">Любимые пилоты и команды</span>
                </div>
              </div>
              <IndexArrow />
            </Link>

            <Link to="/settings" className="menu-item full-width index-wide-link">
              <div className="index-wide-link-left">
                <IndexIcon name="settings" />
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Настройки</span>
                  <span className="index-card-desc">Часовой пояс и уведомления</span>
                </div>
              </div>
              <IndexArrow />
            </Link>

            <Link to="/account" className="menu-item full-width index-wide-link index-account-link">
              <div className="index-wide-link-left">
                <IndexIcon name="account" />
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Аккаунт</span>
                  <span className="index-card-desc">Профиль и безопасность входа</span>
                </div>
              </div>
              <IndexArrow />
            </Link>

            <Link to="/contact-admin" className="menu-item full-width index-wide-link">
              <div className="index-wide-link-left">
                <IndexIcon name="contact" />
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Связаться с админом</span>
                  <span className="index-card-desc">Отправить сообщение в Telegram</span>
                </div>
              </div>
              <IndexArrow />
            </Link>
        </div>
      </div>

      <div className="index-lower-stack">
        <div className="index-panel index-standings-panel">
          <div className="section-title">Положение в чемпионате {nextRace?.season || currentYear}</div>
          <div className="index-standings-grid">
            <div className="index-standings-card">
              <div className="index-standings-title">Пилоты</div>
              <div className="index-standings-table">
                {driversTop.map((d) => (
                  <div key={`${d.position}-${d.name}`} className="index-standings-row">
                    <span>{d.position}</span>
                    <span className="index-standings-entity">
                      {DRIVER_FLAG_BY_CODE[(d.code || "").toUpperCase()] && (
                        <img
                          src={getCountryFlagUrl(DRIVER_FLAG_BY_CODE[(d.code || "").toUpperCase()])}
                          alt={d.code || "flag"}
                          className="index-flag-icon"
                        />
                      )}
                      {d.constructorId || d.constructorName ? (
                        <img
                          src={teamLogoUrl(d.constructorId || "", d.constructorName || "", nextRace?.season || currentYear)}
                          alt=""
                          className="index-standings-logo"
                          onError={(e) => (e.currentTarget.style.display = "none")}
                        />
                      ) : null}
                      <span>{d.name}</span>
                    </span>
                    <span>{d.points}</span>
                  </div>
                ))}
                {driversTop.length === 0 && <div className="index-standings-empty">Нет данных</div>}
              </div>
            </div>
            <div className="index-standings-card">
              <div className="index-standings-title">Команды</div>
              <div className="index-standings-table">
                {constructorsTop.map((t) => (
                  <div key={`${t.position}-${t.name}`} className="index-standings-row">
                    <span>{t.position}</span>
                    <span className="index-standings-entity">
                      {TEAM_FLAG_BY_ID[(t.constructorId || "").toLowerCase()] && (
                        <img
                          src={getCountryFlagUrl(TEAM_FLAG_BY_ID[(t.constructorId || "").toLowerCase()])}
                          alt={t.name}
                          className="index-flag-icon"
                        />
                      )}
                      <img
                        src={teamLogoUrl(t.constructorId || "", t.name, nextRace?.season || currentYear)}
                        alt=""
                        className="index-standings-logo"
                        onError={(e) => (e.currentTarget.style.display = "none")}
                      />
                      <span>{t.name}</span>
                    </span>
                    <span>{t.points}</span>
                  </div>
                ))}
                {constructorsTop.length === 0 && <div className="index-standings-empty">Нет данных</div>}
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>}
    </>
  );
}

export default IndexPage;
