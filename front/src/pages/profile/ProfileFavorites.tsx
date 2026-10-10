import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';

export type ProfileFavoritesData = { drivers: string[]; teams: string[] };

export function ProfileFavorites({ favorites, owner }: { favorites: ProfileFavoritesData; owner: boolean }) {
  const season = new Date().getFullYear();
  const [drivers, setDrivers] = useState<Record<string, string>>({});
  const [teams, setTeams] = useState<Record<string, string>>({});
  const hasDrivers = favorites.drivers.length > 0;
  const hasTeams = favorites.teams.length > 0;
  useEffect(() => {
    if (!hasDrivers) return;
    let active = true;
    void apiRequest<{ drivers?: { code: string; name: string }[] }>('/api/drivers', { season })
      .then(data => { if (active) setDrivers(Object.fromEntries((data.drivers || []).map(driver => [driver.code, driver.name]))); })
      .catch(() => { /* Saved driver codes remain usable when the season catalogue is unavailable. */ });
    return () => { active = false; };
  }, [season, hasDrivers]);
  useEffect(() => {
    if (!hasTeams) return;
    let active = true;
    void apiRequest<{ constructors?: { name: string; constructorId?: string }[] }>('/api/constructors', { season })
      .then(data => { if (active) setTeams(Object.fromEntries((data.constructors || []).filter(team => team.constructorId).map(team => [team.name, team.constructorId!]))); })
      .catch(() => { /* Keep the saved team visible even if the current catalogue is unavailable. */ });
    return () => { active = false; };
  }, [season, hasTeams]);
  return <section className="profile-panel profile-favorites" aria-labelledby="profile-favorites-title">
    <div className="profile-favorites-heading"><h2 id="profile-favorites-title">Избранное</h2>{owner && <Link to="/favorites">Изменить избранное →</Link>}</div>
    <p className="profile-muted">{owner ? 'За кем ты следишь в мире гонок.' : 'За кем следит участник в мире гонок.'}</p>
    {!favorites.drivers.length && !favorites.teams.length ? <p className="profile-muted">{owner ? 'Добавь любимых пилотов и команды — они появятся здесь.' : 'Участник пока не выбрал любимых пилотов и команды.'}</p> : <div className="profile-following">
      <div><h3>Пилоты</h3>{favorites.drivers.length ? <ul>{favorites.drivers.map(code => <li key={code}><Link to={`/driver-details?code=${encodeURIComponent(code)}&season=${season}`}><span className="profile-following-code">{code}</span><span>{drivers[code] || code}</span></Link></li>)}</ul> : <p className="profile-muted">Пилоты не выбраны.</p>}</div>
      <div><h3>Команды</h3>{favorites.teams.length ? <ul>{favorites.teams.map(team => <li key={team}><Link to={teams[team] ? `/constructor-details?constructorId=${encodeURIComponent(teams[team])}&season=${season}` : '/constructors'}><span className="profile-following-star" aria-hidden="true">★</span><span>{team}</span></Link></li>)}</ul> : <p className="profile-muted">Команды не выбраны.</p>}</div>
    </div>}
  </section>;
}
