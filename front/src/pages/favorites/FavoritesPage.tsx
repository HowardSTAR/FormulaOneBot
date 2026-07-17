import { useState, useEffect, useCallback } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { hapticSelection } from "../../helpers/telegram";
import "../../assets/personal-pages.css";

type Driver = { code: string; name: string };
type Team = { name: string };
type FavoritesData = { drivers: string[]; teams: string[] };

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
  const selectedCount = tab === "drivers" ? userFavorites.drivers.length : userFavorites.teams.length;

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
      setError(e instanceof Error ? e.message : "Не удалось обновить избранное");
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
    setError(null);
    setUserFavorites((prev) => ({
      ...prev,
      drivers: prev.drivers.includes(code) ? prev.drivers.filter((c) => c !== code) : [...prev.drivers, code],
    }));
    try {
      await apiRequest("/api/favorites/driver", { id: code }, "POST");
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Не удалось обновить избранное");
      setUserFavorites((prev) => ({
        ...prev,
        drivers: prev.drivers.includes(code) ? prev.drivers.filter((c) => c !== code) : [...prev.drivers, code],
      }));
    }
  };

  const toggleTeam = async (name: string) => {
    hapticSelection();
    setError(null);
    setUserFavorites((prev) => ({
      ...prev,
      teams: prev.teams.includes(name) ? prev.teams.filter((t) => t !== name) : [...prev.teams, name],
    }));
    try {
      await apiRequest("/api/favorites/team", { id: name }, "POST");
    } catch (e) {
      console.error(e);
      setUserFavorites((prev) => ({
        ...prev,
        teams: prev.teams.includes(name) ? prev.teams.filter((t) => t !== name) : [...prev.teams, name],
      }));
    }
  };

  return (
    <div className="personal-page favorites-page">
      <BackButton />
      <header className="personal-page-header">
        <div>
          <span className="personal-page-kicker">Личный раздел</span>
          <h1>Избранное</h1>
          <p>Соберите пилотов и команды, за которыми хотите следить в течение сезона.</p>
        </div>
        <div className="personal-page-summary" aria-label={`Выбрано: ${selectedCount}`}>
          <strong>{selectedCount}</strong><span>выбрано</span>
        </div>
      </header>

      <section className="personal-surface">
        <div className="favorites-toolbar">
          <div>
            <span className="personal-control-label">Категория</span>
            <div className="segmented-tabs">
              <div
                className="segmented-slider"
                style={{ transform: tab === "drivers" ? "translateX(0)" : "translateX(100%)" }}
                aria-hidden
              />
              <button type="button" className={`segmented-tab ${tab === "drivers" ? "active" : ""}`} onClick={() => { hapticSelection(); setTab("drivers"); }}>
                Пилоты
              </button>
              <button type="button" className={`segmented-tab ${tab === "teams" ? "active" : ""}`} onClick={() => { hapticSelection(); setTab("teams"); }}>
                Команды
              </button>
            </div>
          </div>
          <p><i aria-hidden />Изменения сохраняются автоматически</p>
        </div>

        {loading && <div className="personal-loading"><div className="spinner" /><div>Загрузка избранного…</div></div>}
        {error && <div className="personal-error" role="alert">{error}</div>}

      {!loading && tab === "drivers" && (
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
              <button
                type="button"
                key={driver.code}
                className={`select-item ${userFavorites.drivers.includes(driver.code) ? "selected" : ""}`}
                onClick={() => toggleDriver(driver.code)}
                aria-pressed={userFavorites.drivers.includes(driver.code)}
              >
                <div className="item-text-wrap">
                  <div className="item-name">{driver.name}</div>
                  <div className="item-code">{driver.code}</div>
                </div>
                <div className="check-icon">⭐</div>
              </button>
            ))
          )}
        </div>
      )}

      {!loading && tab === "teams" && (
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
              <button
                type="button"
                key={team.name}
                className={`select-item ${userFavorites.teams.includes(team.name) ? "selected" : ""}`}
                onClick={() => toggleTeam(team.name)}
                aria-pressed={userFavorites.teams.includes(team.name)}
              >
                <div className="item-text-wrap">
                  <div className="item-name">{team.name}</div>
                </div>
                <div className="check-icon">⭐</div>
              </button>
            ))
          )}
        </div>
      )}
      </section>
    </div>
  );
}

export default FavoritesPage;
