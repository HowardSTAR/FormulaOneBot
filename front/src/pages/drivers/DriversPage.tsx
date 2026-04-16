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

function pilotPortraitUrl(code: string, fullName: string, season: number): string {
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const params = new URLSearchParams({ season: String(season) });
  if (code) params.set("code", code);
  if (fullName) params.set("name", fullName);
  return `${origin.replace(/\/$/, "")}${pathBase}/api/pilot-portrait?${params.toString()}`;
}

function teamLabel(constructorId?: string, constructorName?: string): string {
  const id = (constructorId || "").toLowerCase();
  if (id === "mercedes") return "MERCEDES-AMG PETRONAS";
  if (id === "ferrari") return "SCUDERIA FERRARI";
  if (id === "mclaren") return "MCLAREN F1 TEAM";
  if (id === "red_bull" || id === "redbull") return "ORACLE RED BULL RACING";
  if (id === "aston_martin") return "ASTON MARTIN ARAMCO";
  return (constructorName || "НЕИЗВЕСТНАЯ КОМАНДА").toUpperCase();
}

type Driver = {
  position: number;
  name: string;
  code: string;
  points: number;
  is_favorite?: boolean;
  number?: string;
  constructorId?: string;
  constructorName?: string;
  driverId?: string;
};

type DriversResponse = { drivers?: Driver[] };
type ConstructorStanding = { position: number; name: string; points: number };
type ConstructorsResponse = { constructors?: ConstructorStanding[] };
type RaceResult = { code?: string; points?: number };
type RaceResultsResponse = { results?: RaceResult[] };
type NextRaceInfo = {
  status?: string;
  event_name?: string;
  date?: string;
  round?: number;
};

function DriversPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const yearFromUrl = parseInt(searchParams.get("year") || "", 10);
  const [year, setYear] = useState(
    yearFromUrl && yearFromUrl >= 1950 && yearFromUrl <= currentRealYear ? yearFromUrl : currentRealYear
  );
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<{ icon: string; title: string; desc: string } | null>(null);
  const [topConstructors, setTopConstructors] = useState<ConstructorStanding[]>([]);
  const [nextRace, setNextRace] = useState<NextRaceInfo | null>(null);
  const [lastRacePointsByCode, setLastRacePointsByCode] = useState<Record<string, number>>({});

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

  const loadDrivers = useCallback(async (season: number) => {
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    try {
      const data = await apiRequest<DriversResponse>("/api/drivers", { season });
      if (!data.drivers || data.drivers.length === 0) {
        if (season === currentRealYear) {
          setEmptyMessage({
            icon: "🏎️",
            title: "Сезон еще не начался",
            desc: "Первая гонка еще впереди. Таблица очков пуста.",
          });
        } else {
          setEmptyMessage({ icon: "", title: "Нет данных", desc: `Информация за ${season} год отсутствует.` });
        }
        setDrivers([]);
      } else {
        setDrivers(data.drivers);
      }
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDrivers(year);
  }, [year, loadDrivers]);

  useEffect(() => {
    let cancelled = false;
    async function loadDesktopAside() {
      try {
        const [constructorsRes, nextRaceRes] = await Promise.allSettled([
          apiRequest<ConstructorsResponse>("/api/constructors", { season: year }),
          apiRequest<NextRaceInfo>("/api/next-race", { season: year }),
        ]);
        if (cancelled) return;
        setTopConstructors(
          constructorsRes.status === "fulfilled" ? (constructorsRes.value.constructors || []).slice(0, 3) : []
        );
        setNextRace(nextRaceRes.status === "fulfilled" ? nextRaceRes.value : null);
      } catch {
        if (!cancelled) {
          setTopConstructors([]);
          setNextRace(null);
        }
      }
    }
    loadDesktopAside();
    return () => {
      cancelled = true;
    };
  }, [year]);

  useEffect(() => {
    let cancelled = false;
    async function loadLastRacePoints() {
      try {
        const res = await apiRequest<RaceResultsResponse>("/api/race-results", { season: year });
        if (cancelled) return;
        const pointsMap: Record<string, number> = {};
        for (const row of res.results || []) {
          const code = String(row.code || "").toUpperCase();
          if (!code) continue;
          pointsMap[code] = Number(row.points || 0);
        }
        setLastRacePointsByCode(pointsMap);
      } catch {
        if (!cancelled) setLastRacePointsByCode({});
      }
    }
    loadLastRacePoints();
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
        icon: "🔮",
        title: "Будущее туманно",
        desc: `Мы пока не знаем, кто станет чемпионом в ${y} году.`,
      });
      setDrivers([]);
      setLoading(false);
      return;
    }
    if (y < 1950) {
      setEmptyMessage({
        icon: "🦖",
        title: "Слишком рано",
        desc: "Первый сезон Формулы-1 прошел в 1950 году.",
      });
      setDrivers([]);
      setLoading(false);
      return;
    }
    updateYear(y);
  };

  const leader = drivers[0] || null;
  const second = drivers[1] || null;
  const gapToLeader = leader && second ? Math.max(0, leader.points - second.points) : 0;
  const teamAccent = (team?: string) => {
    const v = (team || "").toLowerCase();
    if (v.includes("mercedes")) return "#00d2be";
    if (v.includes("ferrari")) return "#e10600";
    if (v.includes("mclaren")) return "#ff8700";
    if (v.includes("red bull")) return "#1d4ed8";
    return "#af8781";
  };

  return (
    <>
      <BackButton>← <span>Главное меню</span></BackButton>
      <div className="page-head-row">
        <h2 className="page-head-title">Личный зачет</h2>
        <div className="page-head-controls mobile-year-control">
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={1950}
            maxYear={currentRealYear}
            placeholder="Введи год"
          />
        </div>
      </div>

      <div className="desktop-standings-layout">
        <div className="desktop-standings-board drivers-desktop-shell">
          <div className="desktop-standings-toolbar drivers-desktop-toolbar">
            <div>
              <div className="drivers-desktop-kicker">Прямые данные · Телеметрия {year}</div>
              <h2 className="desktop-standings-heading">Личный зачет пилотов</h2>
            </div>
            <div className="drivers-desktop-controls">
              <YearSelect
                value={year}
                onChange={handleYearChange}
                minYear={1950}
                maxYear={currentRealYear}
                placeholder="Введи год"
              />
              <button type="button" className="drivers-filter-btn">Фильтры</button>
            </div>
          </div>
          {loading && <div className="loading full-width"><div className="spinner" /><div>Загрузка пилотов...</div></div>}
          {error && <div className="page-error">{error}</div>}
          {!loading && !error && emptyMessage && (
            <div className="empty-state">
              {emptyMessage.icon && <span className="empty-icon">{emptyMessage.icon}</span>}
              <div className="empty-title">{emptyMessage.title}</div>
              <div className="empty-desc">{emptyMessage.desc}</div>
            </div>
          )}
          {!loading && !error && !emptyMessage && drivers.length > 0 && (
            <>
            <div className="desktop-standings-table drivers-standings-table">
              <div className="desktop-standings-table-head">
                <span>Поз</span>
                <span>Пилот</span>
                <span>Команда</span>
                <span>Очки</span>
              </div>
              <div className="drivers-standings-scroll">
                {drivers.map((driver) => {
                  const toDriver = `/driver-details?code=${encodeURIComponent(driver.code)}&season=${year}${driver.driverId ? `&driverId=${encodeURIComponent(driver.driverId)}` : ""}`;
                  return (
                    <div
                      key={`desktop-${driver.code}`}
                      role="button"
                      tabIndex={0}
                      className={`desktop-standings-row pos-${driver.position}`}
                      onClick={() => navigate(toDriver)}
                      onKeyDown={(e) => e.key === "Enter" && navigate(toDriver)}
                    >
                      <span className="desktop-standings-pos">{driver.position}</span>
                      <div className="desktop-standings-driver drivers-row-driver">
                        <img src={pilotPortraitUrl(driver.code, driver.name, year)} alt={driver.name} />
                        <div>
                          <span className="desktop-standings-name">
                            {driver.name}
                            {driver.is_favorite && <b className="drivers-row-favorite">★</b>}
                          </span>
                          <span className="desktop-standings-meta">
                            <i>{driver.code || "DRV"}</i>
                            <u>{driver.number ? `#${driver.number}` : "—"}</u>
                          </span>
                        </div>
                      </div>
                      <div className="drivers-row-team">
                        <i style={{ background: teamAccent(driver.constructorName) }} />
                        <span>{teamLabel(driver.constructorId, driver.constructorName)}</span>
                      </div>
                      <span className="desktop-standings-points">
                        <strong>{driver.points}</strong>
                        <small>
                          {Object.prototype.hasOwnProperty.call(lastRacePointsByCode, (driver.code || "").toUpperCase())
                            ? `+${lastRacePointsByCode[(driver.code || "").toUpperCase()]} очк. за последнюю гонку`
                            : "нет данных за последнюю гонку"}
                        </small>
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="drivers-insights-grid">
              <article className="drivers-insight-card">
                <h4>Отставание от лидера</h4>
                <p>{gapToLeader} ОЧК. <span>({second?.code || "—"} vs {leader?.code || "—"})</span></p>
              </article>
              <article className="drivers-insight-card active">
                <h4>Борьба в чемпионате</h4>
                <p>Высокая интенсивность</p>
                <small>Прогнозы показывают потенциальную битву трех пилотов к 12-му этапу.</small>
              </article>
            </div>
            </>
          )}
        </div>
        <aside className="desktop-standings-sidebar drivers-desktop-sidebar-legacy">
          <div className="desktop-side-card">
            <div className="desktop-side-title">Год</div>
            <YearSelect
              value={year}
              onChange={handleYearChange}
              minYear={1950}
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
            onClick={() => navigate(`/constructors?year=${year}`)}
            onKeyDown={(e) => e.key === "Enter" && navigate(`/constructors?year=${year}`)}
          >
            <div className="desktop-side-title">Топ конструкторов</div>
            {topConstructors.map((t, idx) => (
              <div key={t.name} className={`desktop-side-list-row pos-${idx + 1}`}>
                <span>{t.name}</span>
                <b>{t.points}</b>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="standings-cards-grid">
        {loading && <div className="loading full-width"><div className="spinner" /><div>Загрузка пилотов...</div></div>}
        {error && <div className="page-error">{error}</div>}
        {!loading && !error && emptyMessage && (
          <div className="empty-state">
            {emptyMessage.icon && <span className="empty-icon">{emptyMessage.icon}</span>}
            <div className="empty-title">{emptyMessage.title}</div>
            <div className="empty-desc">{emptyMessage.desc}</div>
          </div>
        )}
        {!loading && !error && !emptyMessage && drivers.length > 0 &&
          drivers.map((driver) => {
            const posClass =
              driver.position === 1 ? "pos-1" : driver.position === 2 ? "pos-2" : driver.position === 3 ? "pos-3" : "";
            const isChampion = driver.position === 1 && year < currentRealYear;
            const toDriver = `/driver-details?code=${encodeURIComponent(driver.code)}&season=${year}${driver.driverId ? `&driverId=${encodeURIComponent(driver.driverId)}` : ""}`;
            return (
              <div
                key={driver.code}
                role="button"
                tabIndex={0}
                className={isChampion ? "driver-card champion-card driver-card-clickable" : "driver-card driver-card-clickable"}
                onClick={() => navigate(toDriver)}
                onKeyDown={(e) => e.key === "Enter" && navigate(toDriver)}
              >
                {isChampion && <div className="champion-badge">Чемпион мира</div>}
                <div className={`pos-box ${posClass}`}>{driver.position}</div>
                <div className="driver-info">
                  <div className="driver-name" style={isChampion ? { color: "#ffd700" } : undefined}>
                    {driver.name} {driver.is_favorite && <span style={{ fontSize: 14, marginLeft: 4 }}>⭐️</span>}
                  </div>
                  <div
                    className="team-name driver-code-row"
                    style={isChampion ? { color: "rgba(255,255,255,0.7)" } : undefined}
                  >
                    {driver.number && (
                      <span className="driver-number">#{driver.number}</span>
                    )}
                    {(driver.constructorId || driver.constructorName) && (
                      <img
                        src={teamLogoUrl(
                          driver.constructorId || "",
                          driver.constructorName || "",
                          year
                        )}
                        alt=""
                        className="driver-team-logo"
                        onError={(e) => (e.currentTarget.style.display = "none")}
                      />
                    )}
                    <span>{driver.code}</span>
                  </div>
                </div>
                <div
                  className="driver-points"
                  style={isChampion ? { background: "#ffd700", color: "#000" } : undefined}
                >
                  {driver.points}
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
}

export default DriversPage;
