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

  return (
    <>
      <BackButton>← <span>Главное меню</span></BackButton>
      <div className="page-head-row">
        <h2 className="page-head-title">Личный зачет</h2>
        <div className="page-head-controls">
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={1950}
            maxYear={currentRealYear}
            placeholder="Введи год"
          />
        </div>
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
                {isChampion && <div className="champion-badge">World Champion</div>}
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
