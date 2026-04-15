import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useHeroData } from "../../context/HeroDataContext";
import { hasTelegramAuth } from "../../helpers/auth";
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
  const isAuthenticated = hasTelegramAuth();
  const currentYear = new Date().getFullYear();
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
    Date.now() >= Math.min(...sessionTimesMs) - 6 * 60 * 60 * 1000 &&
    Date.now() <= Math.max(...sessionTimesMs) + 12 * 60 * 60 * 1000 &&
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
  }, [sessionsForCards, displayTz, nextRace?.race_start_utc]);

  const raceLeader = driversTop[0] || null;
  const qualiLeader = driversTop[1] || driversTop[0] || null;
  const comparePair = [driversTop[0], driversTop[1]].filter(Boolean) as DriverStanding[];
  const voteBase = (driversTop[0]?.points || 0) + (driversTop[1]?.points || 0) || 1;
  const voteA = Math.max(8, Math.min(92, Math.round(((driversTop[0]?.points || 0) / voteBase) * 100)));
  const voteB = Math.max(8, Math.min(92, Math.round(((driversTop[1]?.points || 0) / voteBase) * 100)));

  const shortName = (name?: string): string => {
    if (!name) return "—";
    const parts = name.trim().split(/\s+/);
    return (parts[parts.length - 1] || name).toUpperCase();
  };

  return (
    <>
      <div className="index-desktop-shell">
        <div className="index-hero-wrap index-desktop-hero-wrap">
          <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} />
        </div>

        <div className="index-desktop-widget-grid">
          <Link to="/race-results" className="menu-item index-desktop-widget">
            <div className="index-desktop-widget-head">
              <div>
                <h3 className="index-desktop-widget-title">Race</h3>
                <p className="index-desktop-widget-sub">Official Grand Prix Standings</p>
              </div>
              <span className="index-desktop-widget-icon">🏁</span>
            </div>
            <div className="index-desktop-widget-main">
              <div className="index-desktop-widget-rank">01</div>
              <div className="index-desktop-widget-leader">
                <p>{raceLeader?.name || "Данные скоро"}</p>
                <span>{raceLeader?.constructorName || "Formula One"}</span>
              </div>
              <div className="index-desktop-widget-value">{raceLeader ? `${raceLeader.points} PTS` : "—"}</div>
            </div>
            <div className="index-desktop-widget-btn">View Full Table</div>
          </Link>

          <Link to="/quali-results" className="menu-item index-desktop-widget">
            <div className="index-desktop-widget-head">
              <div>
                <h3 className="index-desktop-widget-title">Qualifying</h3>
                <p className="index-desktop-widget-sub">Pole Position Battle</p>
              </div>
              <span className="index-desktop-widget-icon">⏱</span>
            </div>
            <div className="index-desktop-widget-main">
              <div className="index-desktop-widget-rank">01</div>
              <div className="index-desktop-widget-leader">
                <p>{qualiLeader?.name || "Данные скоро"}</p>
                <span>{qualiLeader?.constructorName || "Formula One"}</span>
              </div>
              <div className="index-desktop-widget-value">{sessionMeta.quali?.time || "--:--"}</div>
            </div>
            <div className="index-desktop-widget-btn">Live Updates</div>
          </Link>

          <Link to="/compare" className="menu-item index-desktop-widget">
            <div className="index-desktop-widget-head">
              <div>
                <h3 className="index-desktop-widget-title">Comparison</h3>
                <p className="index-desktop-widget-sub">Head-to-Head Analysis</p>
              </div>
              <span className="index-desktop-widget-icon">⚔</span>
            </div>
            <div className="index-desktop-versus">
              <div className="index-desktop-avatar">
                <div>{shortName(comparePair[0]?.name).slice(0, 2)}</div>
                <span>{shortName(comparePair[0]?.name)}</span>
              </div>
              <div className="index-desktop-avatar">
                <div>{shortName(comparePair[1]?.name).slice(0, 2)}</div>
                <span>{shortName(comparePair[1]?.name)}</span>
              </div>
            </div>
            <div className="index-desktop-widget-btn">Launch Tool</div>
          </Link>

          <Link to="/voting" className="menu-item index-desktop-widget">
            <div className="index-desktop-widget-head">
              <div>
                <h3 className="index-desktop-widget-title">Voting</h3>
                <p className="index-desktop-widget-sub">Driver of the Day</p>
              </div>
              <span className="index-desktop-widget-icon">🗳</span>
            </div>
            <div className="index-desktop-vote-lines">
              <div className="index-desktop-vote-line">
                <span>{shortName(driversTop[0]?.name)}</span>
                <div className="index-desktop-vote-track"><i style={{ width: `${voteA}%` }} /></div>
                <b>{voteA}%</b>
              </div>
              <div className="index-desktop-vote-line">
                <span>{shortName(driversTop[1]?.name)}</span>
                <div className="index-desktop-vote-track"><i style={{ width: `${voteB}%` }} /></div>
                <b>{voteB}%</b>
              </div>
            </div>
            <div className="index-desktop-widget-btn">Cast Your Vote</div>
          </Link>
        </div>

        <Link to="/season" className="menu-item index-desktop-calendar-cta">
          <div className="index-desktop-calendar-left">
            <span className="index-desktop-calendar-icon">📅</span>
            <div>
              <h3>Full Race Calendar</h3>
              <p>Explore all events of the {nextRace?.season || currentYear} FIA Formula One season.</p>
            </div>
          </div>
          <span className="index-desktop-calendar-arrow">→</span>
        </Link>
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
              <span className="menu-icon">⏱</span>
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
              <span className="menu-icon">🏁</span>
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
                  <span className="menu-icon">⚡🏁</span>
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
                  <span className="menu-icon">⚡⏱</span>
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
    </>
  );
}

export default IndexPage;
