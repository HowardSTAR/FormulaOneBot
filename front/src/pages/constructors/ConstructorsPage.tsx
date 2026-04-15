import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { YearSelect } from "../../components/YearSelect";
import { apiRequest } from "../../helpers/api";

const currentRealYear = new Date().getFullYear();

function teamLogoUrl(teamId: string, teamName: string, season: number): string {
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const team = teamId || teamName;
  const params = new URLSearchParams({ team, season: String(season) });
  if (teamName) params.set("name", teamName);
  return `${origin.replace(/\/$/, "")}${pathBase}/api/team-logo?${params}`;
}

type Constructor = {
  position: number;
  name: string;
  points: number;
  is_favorite?: boolean;
  constructorId?: string;
};

type ConstructorsResponse = { constructors?: Constructor[] };
type DriverStanding = { name: string; points: number };
type DriversResponse = { drivers?: DriverStanding[] };
type NextRaceInfo = {
  status?: string;
  event_name?: string;
  date?: string;
  round?: number;
  location?: string;
};

const minConstructorYear = 1958;

function ConstructorsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const yearFromUrl = parseInt(searchParams.get("year") || "", 10);
  const [year, setYear] = useState(
    yearFromUrl && yearFromUrl >= minConstructorYear && yearFromUrl <= currentRealYear ? yearFromUrl : currentRealYear
  );
  const [teams, setTeams] = useState<Constructor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<{ icon: string; title: string; desc?: string } | null>(null);
  const [topDrivers, setTopDrivers] = useState<DriverStanding[]>([]);
  const [nextRace, setNextRace] = useState<NextRaceInfo | null>(null);

  const formatRaceDate = (isoDate?: string): string => {
    if (!isoDate) return "";
    const parts = isoDate.split("-");
    if (parts.length !== 3) return isoDate;
    const y = Number(parts[0]);
    const m = Number(parts[1]);
    const d = Number(parts[2]);
    if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return isoDate;
    const dt = new Date(Date.UTC(y, m - 1, d));
    return dt.toLocaleDateString("ru-RU", { timeZone: "UTC", day: "numeric", month: "long" });
  };

  const loadTeams = useCallback(async (season: number) => {
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    try {
      const data = await apiRequest<ConstructorsResponse>("/api/constructors", { season });
      if (!data.constructors || data.constructors.length === 0) {
        if (season === currentRealYear) {
          setEmptyMessage({
            icon: "🏎️",
            title: "Сезон еще не начался",
            desc: "Ни одна команда еще не заработала очки.",
          });
        } else {
          setEmptyMessage({ icon: "", title: "Нет данных" });
        }
        setTeams([]);
      } else {
        setTeams(data.constructors);
      }
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTeams(year);
  }, [year, loadTeams]);

  useEffect(() => {
    let cancelled = false;
    async function loadDesktopAside() {
      try {
        const [driversRes, nextRaceRes] = await Promise.allSettled([
          apiRequest<DriversResponse>("/api/drivers", { season: year }),
          apiRequest<NextRaceInfo>("/api/next-race", { season: year }),
        ]);
        if (cancelled) return;
        setTopDrivers(driversRes.status === "fulfilled" ? (driversRes.value.drivers || []).slice(0, 3) : []);
        setNextRace(nextRaceRes.status === "fulfilled" ? nextRaceRes.value : null);
      } catch {
        if (!cancelled) {
          setTopDrivers([]);
          setNextRace(null);
        }
      }
    }
    loadDesktopAside();
    return () => {
      cancelled = true;
    };
  }, [year]);

  const updateYear = useCallback((y: number) => {
    setYear(y);
    setSearchParams(y === currentRealYear ? {} : { year: String(y) }, { replace: true });
  }, [setSearchParams]);

  const handleYearChange = (y: number) => {
    if (y > currentRealYear) {
      setEmptyMessage({
        icon: "🛠️",
        title: "Машина времени сломалась",
        desc: `Инженеры еще не спроектировали болиды ${y} года.`,
      });
      setTeams([]);
      setLoading(false);
      return;
    }
    if (y < minConstructorYear) {
      setEmptyMessage({
        icon: "📜",
        title: "Исторический факт",
        desc: "Кубок Конструкторов разыгрывается только с 1958 года.",
      });
      setTeams([]);
      setLoading(false);
      return;
    }
    updateYear(y);
  };

  const leaderTeam = teams[0] || null;
  const raceDate = nextRace?.date ? new Date(nextRace.date) : null;
  const daysLeft = raceDate
    ? Math.max(
        0,
        Math.ceil((raceDate.getTime() - new Date().setHours(0, 0, 0, 0)) / (1000 * 60 * 60 * 24))
      )
    : null;

  return (
    <>
      <BackButton>← <span>Главное меню</span></BackButton>
      <div className="page-head-row">
        <h2 className="page-head-title">Кубок конструкторов</h2>
        <div className="page-head-controls mobile-year-control">
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={minConstructorYear}
            maxYear={currentRealYear}
            placeholder="Введи год"
          />
        </div>
      </div>

      <div className="desktop-standings-layout">
        <div className="desktop-standings-board constructors-desktop-shell">
          <div className="desktop-standings-toolbar constructors-desktop-toolbar">
            <h2 className="desktop-standings-heading">Constructor Standings</h2>
            <div className="constructors-desktop-subtitle">{year} FIA Formula One World Championship</div>
          </div>

          {loading && <div className="loading full-width"><div className="spinner" /><div>Загрузка команд...</div></div>}
          {error && <div className="page-error">{error}</div>}
          {!loading && !error && emptyMessage && (
            <div className="empty-state">
              {emptyMessage.icon && <span className="empty-icon">{emptyMessage.icon}</span>}
              <div className="empty-title">{emptyMessage.title}</div>
              {emptyMessage.desc && <div className="empty-desc">{emptyMessage.desc}</div>}
            </div>
          )}
          {!loading && !error && !emptyMessage && teams.length > 0 && (
            <>
              <section className="constructors-hero-grid">
                <article className="constructors-leader-card">
                  <div className="constructors-leader-kicker">Current Leader</div>
                  <div className="constructors-leader-main">
                    <span>{leaderTeam?.name || "—"}</span>
                    <b>{leaderTeam?.points ?? 0}</b>
                  </div>
                  <div className="constructors-leader-tags">
                    <span>Dominant Performance</span>
                    <span>+{Math.max(0, (teams[0]?.points ?? 0) - (teams[1]?.points ?? 0))} Pt Lead</span>
                  </div>
                </article>
                <article className="constructors-next-race-card">
                  <div className="constructors-next-kicker">Next Race</div>
                  <h3>{nextRace?.event_name || "Data pending"}</h3>
                  <p>{nextRace?.location || ""}</p>
                  <div className="constructors-next-days">
                    <span>{String(daysLeft ?? 0).padStart(2, "0")}</span>
                    <b>Days Left</b>
                  </div>
                  <button type="button" className="constructors-race-briefing" onClick={() => navigate(`/next-race?season=${year}`)}>
                    Race Briefing
                  </button>
                </article>
              </section>

              <section className="desktop-standings-table constructors-table">
                <div className="desktop-standings-table-head">
                  <span>Rank</span>
                  <span>Constructor</span>
                  <span>Points</span>
                  <span>Action</span>
                </div>
                {teams.map((team) => {
                  const toTeam = `/constructor-details?constructorId=${encodeURIComponent(team.constructorId || team.name)}&season=${year}`;
                  const trendIcon = team.position <= 2 ? "↗" : team.position <= 5 ? "→" : "↘";
                  return (
                    <div
                      key={`desktop-${team.name}`}
                      role="button"
                      tabIndex={0}
                      className={`desktop-standings-row pos-${team.position}`}
                      onClick={() => navigate(toTeam)}
                      onKeyDown={(e) => e.key === "Enter" && navigate(toTeam)}
                    >
                      <span className="desktop-standings-pos">{String(team.position).padStart(2, "0")}</span>
                      <div className="desktop-standings-driver constructors-row-team">
                        {(team.constructorId || team.name) && (
                          <img
                            src={teamLogoUrl(team.constructorId || "", team.name, year)}
                            alt=""
                            className="desktop-standings-team-logo"
                            onError={(e) => (e.currentTarget.style.display = "none")}
                          />
                        )}
                        <span className="desktop-standings-name">
                          {team.name}
                          {team.is_favorite && <i>★</i>}
                        </span>
                      </div>
                      <span className="desktop-standings-points">{team.points}</span>
                      <span className="constructors-row-action">{trendIcon}</span>
                    </div>
                  );
                })}
              </section>

              <section className="constructors-insights-grid">
                <article className="constructors-insight-card">
                  <div className="constructors-insight-title">Technical Analysis</div>
                  <p>
                    {leaderTeam?.name || "Лидер чемпионата"} удерживает преимущество за счет стабильного темпа и
                    минимальных потерь в ключевых секторах.
                  </p>
                </article>
                <article className="constructors-insight-card">
                  <div className="constructors-insight-title">Power Unit Rank</div>
                  <div className="constructors-power-row"><span>{teams[0]?.name || "—"}</span><b>100% Efficiency</b></div>
                  <div className="constructors-power-bar"><i style={{ width: "100%" }} /></div>
                  <div className="constructors-power-row"><span>{teams[1]?.name || "—"}</span><b>98.2% Efficiency</b></div>
                  <div className="constructors-power-bar"><i style={{ width: "98%" }} /></div>
                </article>
                <article className="constructors-insight-card constructors-export-card">
                  <div className="constructors-export-icon">📊</div>
                  <div className="constructors-insight-title">Download Detailed Data</div>
                  <p>JSON / CSV / XLSX available</p>
                  <button type="button">Export Report</button>
                </article>
              </section>
            </>
          )}
        </div>
        <aside className="desktop-standings-sidebar constructors-desktop-sidebar-legacy">
          <div className="desktop-side-card">
            <div className="desktop-side-title">Год</div>
            <YearSelect
              value={year}
              onChange={handleYearChange}
              minYear={minConstructorYear}
              maxYear={currentRealYear}
              placeholder="Введи год"
            />
          </div>
          <div
            className="desktop-side-card clickable"
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/next-race?season=${year}`)}
            onKeyDown={(e) => e.key === "Enter" && navigate(`/next-race?season=${year}`)}
          >
            <div className="desktop-side-title">Предстоящая гонка</div>
            <div className="desktop-side-value">
              {nextRace?.status === "ok" && nextRace?.event_name
                ? `R${String(nextRace.round || "").padStart(2, "0")} · ${nextRace.event_name}`
                : "Данные скоро"}
            </div>
            <div className="desktop-side-muted">{formatRaceDate(nextRace?.date)}</div>
          </div>
          <div
            className="desktop-side-card clickable"
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/drivers?year=${year}`)}
            onKeyDown={(e) => e.key === "Enter" && navigate(`/drivers?year=${year}`)}
          >
            <div className="desktop-side-title">Топ пилотов</div>
            {topDrivers.map((d, idx) => (
              <div key={d.name} className={`desktop-side-list-row pos-${idx + 1}`}>
                <span>{d.name}</span>
                <b>{d.points}</b>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="standings-cards-grid">
        {loading && <div className="loading full-width"><div className="spinner" /><div>Загрузка команд...</div></div>}
        {error && <div className="page-error">{error}</div>}
        {!loading && !error && emptyMessage && (
          <div className="empty-state">
            {emptyMessage.icon && <span className="empty-icon">{emptyMessage.icon}</span>}
            <div className="empty-title">{emptyMessage.title}</div>
            {emptyMessage.desc && <div className="empty-desc">{emptyMessage.desc}</div>}
          </div>
        )}
        {!loading && !error && !emptyMessage && teams.length > 0 &&
          teams.map((team) => {
            const posClass =
              team.position === 1 ? "pos-1" : team.position === 2 ? "pos-2" : team.position === 3 ? "pos-3" : "";
            const isChampion = team.position === 1 && year < currentRealYear;
            const toTeam = `/constructor-details?constructorId=${encodeURIComponent(team.constructorId || team.name)}&season=${year}`;
            return (
              <div
                key={team.name}
                role="button"
                tabIndex={0}
                className={isChampion ? "team-card champion-card team-card-clickable" : "team-card team-card-clickable"}
                onClick={() => navigate(toTeam)}
                onKeyDown={(e) => e.key === "Enter" && navigate(toTeam)}
              >
                {isChampion && <div className="champion-badge">Constructors Champion</div>}
                <div className={`pos-box ${posClass}`}>{team.position}</div>
                {(team.constructorId || team.name) && (
                  <img
                    src={teamLogoUrl(team.constructorId || "", team.name, year)}
                    alt=""
                    className="constructor-logo"
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                )}
                <div className="team-info">
                  <div className="team-name-main" style={isChampion ? { color: "#ffd700" } : undefined}>
                    {team.name} {team.is_favorite && <span style={{ fontSize: 14, marginLeft: 4 }}>⭐️</span>}
                  </div>
                </div>
                <div
                  className="team-points"
                  style={isChampion ? { background: "#ffd700", color: "#000" } : undefined}
                >
                  {team.points}
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
}

export default ConstructorsPage;
