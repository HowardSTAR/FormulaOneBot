import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { YearSelect } from "../../components/YearSelect";
import { apiAssetUrl, apiRequest } from "../../helpers/api";

const currentRealYear = new Date().getFullYear();

function teamLogoUrl(teamId: string, teamName: string, season: number): string {
  const team = teamId || teamName;
  return apiAssetUrl("/api/team-logo", { team, name: teamName, season });
}

function carImageUrl(teamName: string, season: number): string {
  return apiAssetUrl("/api/car-image", { team: teamName, season });
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
  const leaderAdvantage = Math.max(0, (teams[0]?.points ?? 0) - (teams[1]?.points ?? 0));
  const closestBattle = teams.length > 1
    ? teams.slice(1).reduce(
        (closest, team, index) => {
          const previous = teams[index];
          const gap = Math.max(0, previous.points - team.points);
          return gap < closest.gap ? { first: previous, second: team, gap } : closest;
        },
        { first: teams[0], second: teams[1], gap: Math.max(0, teams[0].points - teams[1].points) }
      )
    : null;
  const leaderCarBg = leaderTeam?.name
    ? {
        backgroundImage: `linear-gradient(90deg, rgba(18, 19, 20, 0.72) 0%, rgba(18, 19, 20, 0.86) 68%), url("${carImageUrl(
          leaderTeam.name,
          year
        )}")`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
      }
    : undefined;
  const raceDate = nextRace?.date ? new Date(nextRace.date) : null;
  const daysLeft = raceDate
    ? Math.max(
        0,
        Math.ceil((raceDate.getTime() - new Date().setHours(0, 0, 0, 0)) / (1000 * 60 * 60 * 24))
      )
    : null;

  return (
    <>
      <BackButton className="btn-back constructors-back-button">← <span>Главное меню</span></BackButton>
      <div className="page-head-row">
        <h2 className="page-head-title">Кубок конструкторов</h2>
        <div className="page-head-controls mobile-year-control">
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={minConstructorYear}
            maxYear={currentRealYear}
            placeholder="Введи год"
            showCurrentYearBtn={false}
          />
        </div>
      </div>

      <div className="desktop-standings-layout">
        <div className="desktop-standings-board constructors-desktop-shell">
          <div className="desktop-standings-toolbar constructors-desktop-toolbar">
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
                <article className="constructors-leader-card" style={leaderCarBg}>
                  <div className="constructors-leader-identity">
                    {leaderTeam && (
                      <img
                        src={teamLogoUrl(leaderTeam.constructorId || "", leaderTeam.name, year)}
                        alt=""
                        onError={(e) => (e.currentTarget.style.display = "none")}
                      />
                    )}
                    <div>
                      <div className="constructors-leader-kicker">Лидер чемпионата</div>
                      <div className="constructors-leader-main">
                        <span>{leaderTeam?.name || "—"}</span>
                      </div>
                    </div>
                  </div>
                  <div className="constructors-leader-score">
                    <span>Очки</span>
                    <strong>{leaderTeam?.points ?? 0}</strong>
                  </div>
                  <div className="constructors-leader-tags">
                    <span>1 место</span>
                    <span>+{leaderAdvantage} к ближайшему сопернику</span>
                  </div>
                </article>
                <article className="constructors-next-race-card">
                  <div className="constructors-next-topline">
                    <div className="constructors-next-kicker">Следующий этап</div>
                    <span>{nextRace?.round ? `R${String(nextRace.round).padStart(2, "0")}` : "Ожидается"}</span>
                  </div>
                  <h3>{nextRace?.event_name || "Данные скоро"}</h3>
                  <p>{nextRace?.location || "Место уточняется"} · {formatRaceDate(nextRace?.date)}</p>
                  <div className="constructors-next-footer">
                    <div className="constructors-next-days">
                      <span>{String(daysLeft ?? 0).padStart(2, "0")}</span>
                      <b>дней</b>
                    </div>
                    <button type="button" className="constructors-race-briefing" onClick={() => navigate(`/next-race?season=${year}`)}>
                      Открыть этап →
                    </button>
                  </div>
                </article>
              </section>

              <section className="desktop-standings-table constructors-table">
                <div className="desktop-standings-table-head">
                  <span>Поз</span>
                  <span>Команда</span>
                  <span>Отставание</span>
                  <span>Очки</span>
                </div>
                {teams.map((team) => {
                  const toTeam = `/constructor-details?constructorId=${encodeURIComponent(team.constructorId || team.name)}&season=${year}`;
                  const pointsGap = Math.max(0, (leaderTeam?.points ?? 0) - team.points);
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
                        <div className="constructors-row-copy">
                          <span className="desktop-standings-name">
                            {team.name}
                            {team.is_favorite && <i>★</i>}
                          </span>
                        </div>
                      </div>
                      <span className={`constructors-row-gap ${team.position === 1 ? "leader" : ""}`}>
                        {team.position === 1 ? "Лидер" : `−${pointsGap}`}
                      </span>
                      <span className="desktop-standings-points">
                        <strong>{team.points}</strong>
                        <small>PTS</small>
                      </span>
                    </div>
                  );
                })}
              </section>

              <section className="constructors-season-stats" aria-label="Статистика командного зачёта">
                <article>
                  <span>Команд в зачёте</span>
                  <strong>{teams.length}</strong>
                </article>
                <article>
                  <span>Преимущество лидера</span>
                  <strong>+{leaderAdvantage}</strong>
                  <small>очков</small>
                </article>
                <article>
                  <span>Самая плотная борьба</span>
                  <strong>{closestBattle ? `${closestBattle.gap} очк.` : "—"}</strong>
                  <small>
                    {closestBattle ? `${closestBattle.first.name} / ${closestBattle.second.name}` : "Недостаточно данных"}
                  </small>
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
                {isChampion && <div className="champion-badge">Чемпион среди конструкторов</div>}
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
