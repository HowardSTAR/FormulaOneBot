import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { hapticSelection } from "../../helpers/telegram";

type Driver = { code: string; name: string };
type Team = { name: string };
type FavoritesData = { drivers: string[]; teams: string[] };

function getInitData(): string {
  const tg = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp;
  return tg?.initData ?? "";
}

function FavoritesPage() {
  const [tab, setTab] = useState<"drivers" | "teams">("drivers");
  const [driversList, setDriversList] = useState<Driver[]>([]);
  const [teamsList, setTeamsList] = useState<Team[]>([]);
  const [userFavorites, setUserFavorites] = useState<FavoritesData>({ drivers: [], teams: [] });
  const [driversOutdated, setDriversOutdated] = useState(false);
  const [teamsOutdated, setTeamsOutdated] = useState(false);
  const [displayYearDrivers, setDisplayYearDrivers] = useState(0);
  const [displayYearTeams, setDisplayYearTeams] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const currentYear = new Date().getFullYear();
    try {
      const favoritesData = await apiRequest<FavoritesData>("/api/favorites");
      setUserFavorites({ drivers: favoritesData.drivers || [], teams: favoritesData.teams || [] });

      let driversData = await apiRequest<{ drivers?: Driver[] }>("/api/drivers", { season: currentYear });
      if (!driversData.drivers || driversData.drivers.length === 0) {
        setDisplayYearDrivers(currentYear - 1);
        driversData = await apiRequest("/api/drivers", { season: currentYear - 1 });
        setDriversOutdated(true);
      } else {
        setDisplayYearDrivers(currentYear);
        setDriversOutdated(false);
      }
      setDriversList(driversData.drivers || []);

      let teamsData = await apiRequest<{ constructors?: Team[] }>("/api/constructors", { season: currentYear });
      if (!teamsData.constructors || teamsData.constructors.length === 0) {
        setDisplayYearTeams(currentYear - 1);
        teamsData = await apiRequest("/api/constructors", { season: currentYear - 1 });
        setTeamsOutdated(true);
      } else {
        setDisplayYearTeams(currentYear);
        setTeamsOutdated(false);
      }
      setTeamsList(teamsData.constructors || []);
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Ошибка загрузки данных");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  const toggleDriver = async (code: string) => {
    hapticSelection();
    setUserFavorites((prev) => ({
      ...prev,
      drivers: prev.drivers.includes(code) ? prev.drivers.filter((c) => c !== code) : [...prev.drivers, code],
    }));
    try {
      await fetch(new URL("/api/favorites/driver", window.location.origin).toString(), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": getInitData() },
        body: JSON.stringify({ id: code }),
      });
    } catch (e) {
      console.error(e);
      setUserFavorites((prev) => ({
        ...prev,
        drivers: prev.drivers.includes(code) ? prev.drivers.filter((c) => c !== code) : [...prev.drivers, code],
      }));
    }
  };

  const toggleTeam = async (name: string) => {
    hapticSelection();
    setUserFavorites((prev) => ({
      ...prev,
      teams: prev.teams.includes(name) ? prev.teams.filter((t) => t !== name) : [...prev.teams, name],
    }));
    try {
      await fetch(new URL("/api/favorites/team", window.location.origin).toString(), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": getInitData() },
        body: JSON.stringify({ id: name }),
      });
    } catch (e) {
      console.error(e);
      setUserFavorites((prev) => ({
        ...prev,
        teams: prev.teams.includes(name) ? prev.teams.filter((t) => t !== name) : [...prev.teams, name],
      }));
    }
  };

  return (
    <>
      <Link to="/" className="btn-back">
        ← <span>Главное меню</span>
      </Link>
      <h2>Избранное</h2>
      <p style={{ marginBottom: 20 }}>Выбери пилотов и команды для отслеживания:</p>

      <div className="segmented-tabs">
        <div
          className="segmented-slider"
          style={{ transform: tab === "drivers" ? "translateX(0)" : "translateX(100%)" }}
          aria-hidden
        />
        <button
          type="button"
          className={`segmented-tab ${tab === "drivers" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setTab("drivers");
          }}
        >
          Пилоты
        </button>
        <button
          type="button"
          className={`segmented-tab ${tab === "teams" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setTab("teams");
          }}
        >
          Команды
        </button>
      </div>

      {loading && <div className="loading full-width">Загрузка...</div>}
      {error && <div style={{ color: "red", textAlign: "center", marginTop: 20 }}>{error}</div>}

      {!loading && !error && tab === "drivers" && (
        <div className="grid-select">
          {driversOutdated && (
            <div className="season-warning">
              <div className="warning-icon">⚠️</div>
              <div className="warning-text">
                <div className="warning-title">Межсезонье</div>
                Список на новый сезон еще не утвержден.<br />Показываем составы {displayYearDrivers} года.
              </div>
            </div>
          )}
          {driversList.length === 0 ? (
            <div style={{ gridColumn: "1 / -1", textAlign: "center" }}>Список пилотов пуст</div>
          ) : (
            driversList.map((driver) => (
              <div
                key={driver.code}
                role="button"
                tabIndex={0}
                className={`select-item ${userFavorites.drivers.includes(driver.code) ? "selected" : ""}`}
                onClick={() => toggleDriver(driver.code)}
                onKeyDown={(e) => e.key === "Enter" && toggleDriver(driver.code)}
              >
                <div className="item-text-wrap">
                  <div className="item-name">{driver.name}</div>
                  <div className="item-code">{driver.code}</div>
                </div>
                <div className="check-icon">⭐</div>
              </div>
            ))
          )}
        </div>
      )}

      {!loading && !error && tab === "teams" && (
        <div className="grid-select">
          {teamsOutdated && (
            <div className="season-warning">
              <div className="warning-icon">⚠️</div>
              <div className="warning-text">
                <div className="warning-title">Межсезонье</div>
                Список на новый сезон еще не утвержден.<br />Показываем составы {displayYearTeams} года.
              </div>
            </div>
          )}
          {teamsList.length === 0 ? (
            <div style={{ gridColumn: "1 / -1", textAlign: "center" }}>Список команд пуст</div>
          ) : (
            teamsList.map((team) => (
              <div
                key={team.name}
                role="button"
                tabIndex={0}
                className={`select-item ${userFavorites.teams.includes(team.name) ? "selected" : ""}`}
                onClick={() => toggleTeam(team.name)}
                onKeyDown={(e) => e.key === "Enter" && toggleTeam(team.name)}
              >
                <div className="item-text-wrap">
                  <div className="item-name">{team.name}</div>
                </div>
                <div className="check-icon">⭐</div>
              </div>
            ))
          )}
        </div>
      )}
    </>
  );
}

export default FavoritesPage;
