import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useHeroData } from "../../context/useHeroData";
import { useAuthState } from "../../helpers/auth";
import { apiAssetUrl, apiRequest } from "../../helpers/api";
import { getDisplayTimezone } from "../../helpers/timezone";
import { getCountryFlagUrl } from "../../constants/flags";
import "./styles.css";
import Hero from "./Hero";

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
type ScheduleResponse = { sessions?: SessionItem[] };

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

type IndexIconName =
  | "quali"
  | "race"
  | "sprint"
  | "drivers"
  | "teams"
  | "compare"
  | "vote"
  | "predictions"
  | "wiki"
  | "contact"
  | "calendar"
  | "reaction"
  | "grid"
  | "favorite"
  | "settings"
  | "account";

function IndexIcon({ name }: { name: IndexIconName }) {
  const paths: Record<IndexIconName, React.ReactNode> = {
    quali: <><circle cx="12" cy="13" r="8" /><path d="M12 9v4l3 2M9 2h6M12 5V2" /></>,
    race: <><path d="M5 21V4M5 5c5-3 8 3 14 0v9c-6 3-9-3-14 0" /><path d="M9 5v4M13 6v4M17 6v4M5 10h4M9 9h4M13 10h4" /></>,
    sprint: <path d="m13 2-8 12h6l-1 8 9-13h-6z" />,
    drivers: <><circle cx="12" cy="8" r="4" /><path d="M4 21c.8-5 3.5-7 8-7s7.2 2 8 7" /></>,
    teams: <><path d="M3 15h18l-2-6H8L5 12H3zM5 15v3M19 15v3" /><circle cx="7" cy="18" r="2" /><circle cx="17" cy="18" r="2" /></>,
    compare: <><path d="M7 4 3 8l4 4M3 8h15M17 20l4-4-4-4M21 16H6" /></>,
    vote: <><path d="M8 3h8v5H8zM5 9h14l2 4v8H3v-8z" /><path d="m9 14 2 2 4-5" /></>,
    predictions: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /><path d="m4 7 6-4 6 7 5-5" /></>,
    wiki: <><path d="M4 4.5A3.5 3.5 0 0 1 7.5 1H12v19H7.5A3.5 3.5 0 0 0 4 23.5z" /><path d="M20 4.5A3.5 3.5 0 0 0 16.5 1H12v19h4.5a3.5 3.5 0 0 1 3.5 3.5z" /></>,
    contact: <><path d="M4 4h16v13H8l-4 4z" /><path d="M8 9h8M8 13h5" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4M16 3v4M3 10h18M8 14h2M14 14h2M8 18h2" /></>,
    reaction: <><rect x="7" y="2" width="10" height="20" rx="5" /><circle cx="12" cy="7" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="12" cy="17" r="2" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    favorite: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    account: <><circle cx="9" cy="8" r="4" /><path d="M2 21c.7-4.6 3-7 7-7 2 0 3.6.6 4.8 1.7M16 19l2 2 4-5" /></>,
  };
  return <span className={`menu-icon index-menu-icon is-${name}`} aria-hidden><svg viewBox="0 0 24 24">{paths[name]}</svg></span>;
}

function IndexArrow() {
  return <svg className="index-link-arrow" viewBox="0 0 24 24" aria-hidden><path d="m9 5 7 7-7 7" /></svg>;
}

function IndexPage() {
  const { nextRace, schedule, userTz, loaded, load } = useHeroData();
  const auth = useAuthState();
  const isAuthenticated = auth.signedIn;
  const currentYear = new Date().getFullYear();
  const [renderedAt] = useState(() => Date.now());
  const [driversTop, setDriversTop] = useState<DriverStanding[]>([]);
  const [constructorsTop, setConstructorsTop] = useState<ConstructorStanding[]>([]);
  const [weekendSessions, setWeekendSessions] = useState<SessionItem[]>([]);
  const displayTz = getDisplayTimezone(userTz);
  const sessionsForCards = schedule.length ? schedule : weekendSessions;

  const hasSprintSession = sessionsForCards.some((s) => {
    const n = (s.name || "").toLowerCase();
    return n.includes("спринт") || n.includes("sprint");
  });

  const sessionTimesMs = sessionsForCards
    .map((s) => (s.utc_iso ? new Date(s.utc_iso).getTime() : NaN))
    .filter((v) => !Number.isNaN(v));

  const isSprintWeekendActive =
    hasSprintSession &&
    sessionTimesMs.length > 0 &&
    renderedAt >= Math.min(...sessionTimesMs) - 6 * 60 * 60 * 1000 &&
    renderedAt <= Math.max(...sessionTimesMs) + 12 * 60 * 60 * 1000 &&
    nextRace?.status === "ok";

  useEffect(() => {
    if (!loaded) load();
  }, [loaded, load]);

  useEffect(() => {
    let cancelled = false;
    const season = nextRace?.season || currentYear;
    const loadStandings = async () => {
      try {
        const [driversRes, constructorsRes] = await Promise.allSettled([
          apiRequest<DriversResponse>("/api/drivers", { season }),
          apiRequest<ConstructorsResponse>("/api/constructors", { season }),
        ]);
        if (cancelled) return;
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
  }, [nextRace?.season, currentYear]);

  useEffect(() => {
    let cancelled = false;
    const loadWeekendForCards = async () => {
      if (schedule.length > 0) return;
      if (!nextRace?.season || !nextRace?.round) return;
      try {
        const data = await apiRequest<ScheduleResponse>("/api/weekend-schedule", {
          season: nextRace.season,
          round_number: nextRace.round,
        });
        if (!cancelled) setWeekendSessions(data.sessions || []);
      } catch {
        if (!cancelled) setWeekendSessions([]);
      }
    };
    loadWeekendForCards();
    return () => {
      cancelled = true;
    };
  }, [schedule.length, nextRace?.season, nextRace?.round]);

  const sessionMeta = useMemo(() => {
    const normalizedSessions = sessionsForCards.filter((s) => Boolean(s.utc_iso));
    const parse = (nameMatcher: (n: string) => boolean) => {
      const target = normalizedSessions.find((s) => {
        const n = (s.name || "").toLowerCase().trim();
        return Boolean(s.utc_iso) && nameMatcher(n);
      });
      if (!target?.utc_iso) return null;
      const dt = new Date(target.utc_iso);
      if (Number.isNaN(dt.getTime())) return null;
      return {
        date: dt.toLocaleDateString("ru-RU", {
          timeZone: displayTz,
          day: "numeric",
          month: "long",
        }),
        time: dt.toLocaleTimeString("ru-RU", {
          timeZone: displayTz,
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
    };
    return {
      race:
        parse((n) => n.includes("гонк") || n.includes("race")) ||
        (nextRace?.race_start_utc
          ? (() => {
              const dt = new Date(nextRace.race_start_utc as string);
              if (Number.isNaN(dt.getTime())) return null;
              return {
                date: dt.toLocaleDateString("ru-RU", {
                  timeZone: displayTz,
                  day: "numeric",
                  month: "long",
                }),
                time: dt.toLocaleTimeString("ru-RU", {
                  timeZone: displayTz,
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              };
            })()
          : null),
      quali: parse((n) => n.includes("квали") || n.includes("qualifying")),
      sprint: parse((n) => n === "спринт" || n === "sprint"),
      sprintQuali: parse((n) => n.includes("спринт-квали") || n.includes("sprint qualifying")),
    };
  }, [sessionsForCards, displayTz, nextRace]);

  const widgetSeason = nextRace?.season || currentYear;

  const desktopSessions = useMemo(() => {
    return sessionsForCards
      .filter((session) => Boolean(session.utc_iso))
      .map((session) => ({ session, date: new Date(session.utc_iso as string) }))
      .filter(({ date }) => !Number.isNaN(date.getTime()))
      .sort((a, b) => a.date.getTime() - b.date.getTime())
      .slice(0, 5)
      .map(({ session, date }) => {
        const start = date.getTime();
        const status = renderedAt < start ? "upcoming" : renderedAt <= start + 90 * 60 * 1000 ? "live" : "done";
        return {
          name: session.name,
          day: date.toLocaleDateString("ru-RU", {
            timeZone: displayTz,
            weekday: "short",
            day: "numeric",
            month: "short",
          }),
          time: date.toLocaleTimeString("ru-RU", {
            timeZone: displayTz,
            hour: "2-digit",
            minute: "2-digit",
          }),
          status,
        };
      });
  }, [sessionsForCards, displayTz, renderedAt]);

  return (
    <>
      <div className="index-desktop-shell index-dashboard">
        <section className="index-dashboard-top">
          <div className="index-hero-wrap index-desktop-hero-wrap">
            <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} showTrackMap />
          </div>

          <aside className="index-weekend-board">
            <div className="index-dashboard-section-head">
              <div>
                <span>Этап {nextRace?.round || "—"} · {nextRace?.season || currentYear}</span>
                <h2>Расписание уик-энда</h2>
              </div>
              <Link to="/season">Весь сезон <b aria-hidden>↗</b></Link>
            </div>
            <div className="index-weekend-location">
              <span>{nextRace?.location || nextRace?.country || "Formula 1"}</span>
              <small>Время: {displayTz}</small>
            </div>
            <div className="index-session-list">
              {desktopSessions.length > 0 ? desktopSessions.map((session) => (
                <div key={`${session.name}-${session.day}-${session.time}`} className={`index-session-row is-${session.status}`}>
                  <i aria-hidden />
                  <div>
                    <strong>{session.name}</strong>
                    <span>{session.day}</span>
                  </div>
                  <time>{session.time}</time>
                  {session.status === "live" && <b>LIVE</b>}
                </div>
              )) : (
                <div className="index-session-empty">Расписание загружается из API…</div>
              )}
            </div>
          </aside>
        </section>

        {auth.loaded && !isAuthenticated && (
          <section className="index-guest-strip">
            <div className="index-guest-message">
              <span className="index-guest-icon" aria-hidden>✓</span>
              <div><strong>Вы смотрите сайт как гость</strong><small>Все основные данные Formula 1 уже доступны</small></div>
            </div>
            <div className="index-guest-features" aria-label="Доступно без регистрации">
              <span>Календарь</span><span>Live-расписание</span><span>Результаты</span><span>Таблицы</span><span>Сравнение</span>
            </div>
            <small className="index-guest-note">Вход нужен только для избранного, настроек и голосований</small>
          </section>
        )}

        <section className="index-dashboard-main">
          <div className="index-standings-preview">
            <div className="index-dashboard-section-head index-standings-preview-head">
              <div>
                <span>Чемпионат {widgetSeason}</span>
                <h2>Положение после этапа</h2>
              </div>
              <span className="index-data-badge"><i aria-hidden />Данные API</span>
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

          <aside className="index-quick-panel">
            <div className="index-dashboard-section-head">
              <div><span>Быстрый доступ</span><h2>Главное сейчас</h2></div>
            </div>
            <div className="index-quick-links">
              <Link to="/race-results">
                <span>01</span><div><strong>Результаты гонки</strong><small>{sessionMeta.race ? `${sessionMeta.race.date} · ${sessionMeta.race.time}` : "Последний завершённый этап"}</small></div><b>→</b>
              </Link>
              <Link to="/quali-results">
                <span>02</span><div><strong>Квалификация</strong><small>{sessionMeta.quali ? `${sessionMeta.quali.date} · ${sessionMeta.quali.time}` : "Протокол и стартовая решётка"}</small></div><b>→</b>
              </Link>
              <Link to="/compare">
                <span>03</span><div><strong>Сравнить пилотов</strong><small>Очки, темп и результаты</small></div><b>→</b>
              </Link>
              <Link to="/season">
                <span>04</span><div><strong>Календарь сезона</strong><small>Все {widgetSeason} этапы и трассы</small></div><b>→</b>
              </Link>
              <Link to="/wiki">
                <span>05</span><div><strong>Wiki для новичков</strong><small>Термины и правила F1</small></div><b>→</b>
              </Link>
            </div>
          </aside>
        </section>
      </div>

      <div className="index-mobile-stack">
      <div className="index-layout">
        <div className="index-hero-wrap">
          <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} />
        </div>

        <div className="index-panel index-results-panel">
          <div className="section-title">Последний этап</div>
          <div className="results-grid">
            <Link to="/quali-results" className="menu-item index-result-tile">
              <IndexIcon name="quali" />
              <span className="menu-label index-card-title">Квалификация</span>
              {sessionMeta.quali ? (
                <span className="index-card-meta">
                  <span>{sessionMeta.quali.date}</span>
                  <span>Старт: {sessionMeta.quali.time}</span>
                </span>
              ) : (
                <span className="index-card-meta">
                  <span>Данные скоро</span>
                  <span>Старт: --:--</span>
                </span>
              )}
            </Link>
            <Link to="/race-results" className="menu-item index-result-tile">
              <IndexIcon name="race" />
              <span className="menu-label index-card-title">Гонка</span>
              {sessionMeta.race ? (
                <span className="index-card-meta">
                  <span>{sessionMeta.race.date}</span>
                  <span>Старт: {sessionMeta.race.time}</span>
                </span>
              ) : (
                <span className="index-card-meta">
                  <span>Данные скоро</span>
                  <span>Старт: --:--</span>
                </span>
              )}
            </Link>
            {isSprintWeekendActive && (
              <>
                <Link to="/sprint-results" className="menu-item index-result-tile">
                  <IndexIcon name="sprint" />
                  <span className="menu-label index-card-title">Спринт</span>
                  {sessionMeta.sprint ? (
                    <span className="index-card-meta">
                      <span>{sessionMeta.sprint.date}</span>
                      <span>Старт: {sessionMeta.sprint.time}</span>
                    </span>
                  ) : (
                    <span className="index-card-desc">Короткая гонка уик-энда</span>
                  )}
                </Link>
                <Link to="/sprint-quali-results" className="menu-item index-result-tile">
                  <IndexIcon name="quali" />
                  <span className="menu-label index-card-title">Спринт-квала</span>
                  {sessionMeta.sprintQuali ? (
                    <span className="index-card-meta">
                      <span>{sessionMeta.sprintQuali.date}</span>
                      <span>Старт: {sessionMeta.sprintQuali.time}</span>
                    </span>
                  ) : (
                    <span className="index-card-desc">Стартовая решетка спринта</span>
                  )}
                </Link>
              </>
            )}
          </div>
        </div>

        <div className="index-panel index-season-panel">
          <div className="section-title" id="season-title">
            Сезон {currentYear}
          </div>

          <div className="menu-grid index-quick-grid">
            <Link to="/drivers" className="menu-item index-nav-card">
              <IndexIcon name="drivers" />
              <span className="menu-label index-card-title">Пилоты</span>
              <span className="index-card-desc">Личный зачет и форма</span>
            </Link>
            <Link to="/constructors" className="menu-item index-nav-card">
              <IndexIcon name="teams" />
              <span className="menu-label index-card-title">Команды</span>
              <span className="index-card-desc">Кубок конструкторов</span>
            </Link>
            <Link to="/compare" className="menu-item index-nav-card">
              <IndexIcon name="compare" />
              <span className="menu-label index-card-title">Сравнение</span>
              <span className="index-card-desc">Очки, темп и дуэли</span>
            </Link>
            <Link to="/voting" className="menu-item index-nav-card">
              <IndexIcon name="vote" />
              <span className="menu-label index-card-title">Голосование</span>
              <span className="index-card-desc">Оценки и итоги этапов</span>
            </Link>
            <Link to="/predictions" className="menu-item index-nav-card">
              <IndexIcon name="predictions" />
              <span className="menu-label index-card-title">Прогнозы</span>
              <span className="index-card-desc">Состав этапа и общий зачёт</span>
            </Link>
            <Link to="/wiki" className="menu-item index-nav-card">
              <IndexIcon name="wiki" />
              <span className="menu-label index-card-title">Wiki F1</span>
              <span className="index-card-desc">Термины и правила для новичков</span>
            </Link>
          </div>
          <Link to="/season" className="menu-item full-width index-wide-link index-calendar-main-link">
            <div className="index-wide-link-left">
              <IndexIcon name="calendar" />
              <div className="index-wide-link-text">
                <span className="menu-label index-card-title">Календарь</span>
                <span className="index-card-desc">Расписание и этапы сезона</span>
              </div>
            </div>
            <IndexArrow />
          </Link>
        </div>

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
          </div>
        </div>

        <div className="index-my-section index-panel">
            <div className="section-title">Моё</div>
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
      </div>
    </>
  );
}

export default IndexPage;
