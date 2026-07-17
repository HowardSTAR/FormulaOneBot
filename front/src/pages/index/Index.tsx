import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useHeroData } from "../../context/HeroDataContext";
import { useAuthState } from "../../helpers/auth";
import { apiRequest } from "../../helpers/api";
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
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const team = teamId || teamName;
  const params = new URLSearchParams({ team, season: String(season) });
  if (teamName) params.set("name", teamName);
  return `${origin.replace(/\/$/, "")}${pathBase}/api/team-logo?${params}`;
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
            <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} />
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
              <span className="menu-label index-card-title">Пилоты</span>
              <span className="index-card-desc">Личный зачет и форма</span>
            </Link>
            <Link to="/constructors" className="menu-item index-nav-card">
              <span className="menu-label index-card-title">Команды</span>
              <span className="index-card-desc">Кубок конструкторов</span>
            </Link>
            <Link to="/compare" className="menu-item index-nav-card">
              <span className="menu-label index-card-title">Сравнение</span>
              <span className="index-card-desc">Очки, темп и дуэли</span>
            </Link>
            <Link to="/voting" className="menu-item index-nav-card">
              <span className="menu-label index-card-title">Голосование</span>
              <span className="index-card-desc">Оценки и итоги этапов</span>
            </Link>
          </div>
        </div>

        <div className="index-my-section index-panel">
            <div className="section-title">Моё</div>
            <Link to="/favorites" className="menu-item full-width index-wide-link index-favorites-link">
              <div className="index-wide-link-left">
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Избранное</span>
                  <span className="index-card-desc">Любимые пилоты и команды</span>
                </div>
              </div>
            </Link>

            <Link to="/settings" className="menu-item full-width index-wide-link">
              <div className="index-wide-link-left">
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Настройки</span>
                  <span className="index-card-desc">Часовой пояс и уведомления</span>
                </div>
              </div>
            </Link>

            <Link to="/account" className="menu-item full-width index-wide-link index-account-link">
              <div className="index-wide-link-left">
                <div className="index-wide-link-text">
                  <span className="menu-label index-card-title">Аккаунт</span>
                  <span className="index-card-desc">Профиль и безопасность входа</span>
                </div>
              </div>
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

        <Link to="/season" className="menu-item full-width index-wide-link index-calendar-main-link">
          <div className="index-wide-link-left">
            <div className="index-wide-link-text">
              <span className="menu-label index-card-title">Календарь</span>
              <span className="index-card-desc">Расписание и этапы сезона</span>
            </div>
          </div>
        </Link>
      </div>
      </div>
    </>
  );
}

export default IndexPage;
