import { useState, useEffect, useCallback, useRef } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { hapticSelection } from "../../helpers/telegram";
import { DriverPortrait } from '../../components/DriverPortrait';
import { TeamLogo } from '../../components/TeamLogo';
import { HomeIcon } from '../index/HomeIcon';
import './favorites.css';
import { HomeFavorites } from './HomeFavorites';

type Driver = { code: string; name: string };
type Team = { name: string; constructorId?: string };
type FavoritesData = { drivers: string[]; teams: string[]; home?: { drivers: string[]; teams: string[] } };

function FavoritesPage({ embedded = false }: { embedded?: boolean }) {
  const [tab, setTab] = useState<"drivers" | "teams">("drivers");
  const [driversList, setDriversList] = useState<Driver[]>([]);
  const [teamsList, setTeamsList] = useState<Team[]>([]);
  const [userFavorites, setUserFavorites] = useState<FavoritesData>({ drivers: [], teams: [] });
  const [homeDirty, setHomeDirty] = useState(false);
  const [home, setHome] = useState<FavoritesData>();
  const [firstChoice, setFirstChoice] = useState(false);
  const [driversOutdated, setDriversOutdated] = useState(false);
  const [teamsOutdated, setTeamsOutdated] = useState(false);
  const [displayYearDrivers, setDisplayYearDrivers] = useState(0);
  const [displayYearTeams, setDisplayYearTeams] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pendingRef = useRef(new Set<string>());
  const [pending, setPending] = useState<string[]>([]);
  const selectedCount = tab === "drivers" ? userFavorites.drivers.length : userFavorites.teams.length;
  const unavailable = tab === "drivers"
    ? userFavorites.drivers.filter(code => !driversList.some(d => d.code === code))
    : userFavorites.teams.filter(name => !teamsList.some(t => t.name === name));

  const loadAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const currentYear = new Date().getFullYear();
    try {
      const favoritesData = await apiRequest<FavoritesData>("/api/favorites");
      setUserFavorites({ drivers: favoritesData.drivers || [], teams: favoritesData.teams || [] });
      setHome(favoritesData.home);

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

  const toggleFavorite = async (kind: "drivers" | "teams", value: string) => {
    if (homeDirty && !window.confirm('Выбор для главной не сохранён. Изменить избранное и сбросить этот выбор?')) return;
    setHomeDirty(false);
    const key = `${kind}:${value}`;
    if (pendingRef.current.has(key)) return;
    pendingRef.current.add(key);
    setPending([...pendingRef.current]);
    hapticSelection();
    setError(null);
    const toggle = (prev: FavoritesData): FavoritesData => ({
      ...prev, [kind]: prev[kind].includes(value) ? prev[kind].filter(item => item !== value) : [...prev[kind], value],
    });
    const first = !userFavorites.drivers.length && !userFavorites.teams.length;
    setUserFavorites(toggle);
    try {
      await apiRequest(`/api/favorites/${kind === "drivers" ? "driver" : "team"}`, { id: value }, "POST");
      if (first) setFirstChoice(true);
    } catch (e) {
      setUserFavorites(toggle);
      setError(e instanceof Error ? e.message : "Не удалось сохранить выбор. Попробуйте ещё раз.");
    } finally {
      pendingRef.current.delete(key);
      setPending([...pendingRef.current]);
    }
  };

  const season = tab === "drivers" ? displayYearDrivers : displayYearTeams;
  const outdated = tab === "drivers" ? driversOutdated : teamsOutdated;
  const entries = tab === "drivers"
    ? driversList.map(driver => ({ value: driver.code, name: driver.name, code: driver.code, id: undefined }))
    : teamsList.map(team => ({ value: team.name, name: team.name, code: undefined, id: team.constructorId }));

  return (
    <div className="favorites-page">
      {!embedded && <BackButton />}
      <header className="favorites-header">
        <h1>Избранное</h1>
        <p>Добавьте любимых пилотов и команды. Для главной можно выбрать двух пилотов и одну команду в блоке ниже.</p>
      </header>
      {!loading && <HomeFavorites key={JSON.stringify([userFavorites, home])} favorites={userFavorites} initial={home} names={Object.fromEntries(driversList.map(driver => [driver.code, driver.name]))} busy={pending.length > 0} onSaved={setHome} onDirty={setHomeDirty} />}
      {firstChoice && <p className="favorites-message" role="status">Избранное добавлено. На главной показываем двух пилотов и одну команду. Выбрать их можно в блоке «Кто на главной» выше; вернуться сюда — через «Настройки → Кто на главной».</p>}
      <section className="favorites-panel" aria-label="Выбор избранного" aria-busy={loading}>
        <div className="favorites-controls">
          <div className="favorites-categories" role="group" aria-label="Категория">
            {([['drivers', 'Пилоты'], ['teams', 'Команды']] as const).map(([value, label]) =>
              <button key={value} type="button" aria-pressed={tab === value} onClick={() => { hapticSelection(); setTab(value); }}>{label}<span>{userFavorites[value].length}</span></button>
            )}
          </div>
          <p className="favorites-save-status" role="status">{pending.length ? 'Сохранение…' : 'Изменения сохраняются автоматически'}</p>
        </div>
        {loading && <p className="favorites-message" role="status">Загрузка избранного…</p>}
        {error && <div className="favorites-error" role="alert"><p>{error}</p>{!driversList.length && !teamsList.length && <button type="button" onClick={() => void loadAllData()}>Повторить загрузку</button>}</div>}
        {!loading && <>
          <div className="favorites-list-heading"><h2>{tab === 'drivers' ? 'Пилоты' : 'Команды'}{season > 0 && <span> · {season}</span>}</h2><p>Выбрано: {selectedCount}</p></div>
          {outdated && <p className="favorites-message">Список на новый сезон ещё не утверждён. Показываем составы {season} года.</p>}
          {unavailable.length > 0 && <div className="favorites-archive"><h3>Из прошлых сезонов</h3><p>Эти участники тоже включены в счётчик.</p><div>{unavailable.map(value => <button key={value} type="button" disabled={pending.includes(`${tab}:${value}`)} data-analytics-action="favorites_toggle" onClick={() => void toggleFavorite(tab, value)}>{value}<span>Убрать из избранного</span></button>)}</div></div>}
          {!entries.length ? <p className="favorites-message">{tab === 'drivers' ? 'Список пилотов пуст' : 'Список команд пуст'}</p> : <div className="favorites-grid">
            {entries.map(entry => {
              const selected = userFavorites[tab].includes(entry.value);
              return <button type="button" key={`${tab}:${entry.value}`} className="favorite-choice" aria-pressed={selected} disabled={pending.includes(`${tab}:${entry.value}`)} data-analytics-action="favorites_toggle" onClick={() => void toggleFavorite(tab, entry.value)}>
                <span className="favorite-art">{entry.code ? <DriverPortrait code={entry.code} name={entry.name} season={season} /> : <TeamLogo name={entry.name} id={entry.id} season={season} size={64} />}</span>
                <span className="favorite-name"><strong>{entry.name}</strong>{entry.code && <small>{entry.code}</small>}</span>
                <span className="favorite-star" aria-hidden="true"><HomeIcon name="favorite" /></span>
              </button>;
            })}
          </div>}
        </>}
      </section>
    </div>
  );
}

export default FavoritesPage;
