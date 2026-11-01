import { useEffect, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { DriverPortrait } from '../../components/DriverPortrait';
import { TeamLogo } from '../../components/TeamLogo';
import { HomeIcon } from '../index/HomeIcon';

export type ProfileFavoritesData = { drivers: string[]; teams: string[] };

export function ProfileFavorites({ favorites, owner }: { favorites: ProfileFavoritesData; owner: boolean }) {
  const season = new Date().getFullYear();
  const [drivers, setDrivers] = useState<Record<string, string>>({});
  const [teams, setTeams] = useState<Record<string, string>>({});
  const hasDrivers = favorites.drivers.length > 0;
  const hasTeams = favorites.teams.length > 0;
  const artwork = Array.from({ length: Math.max(favorites.drivers.length, favorites.teams.length) }).flatMap((_, index) => [
    ...(favorites.drivers[index] ? [{ kind: 'driver' as const, value: favorites.drivers[index] }] : []),
    ...(favorites.teams[index] ? [{ kind: 'team' as const, value: favorites.teams[index] }] : []),
  ]);
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
    <div className="profile-section-backdrop profile-favorites-backdrop" aria-hidden="true">
      <HomeIcon name="favorite" />
      <div className="profile-favorites-collage" style={{ '--favorite-columns': Math.min(4, artwork.length) || 1, '--favorite-mobile-columns': Math.min(3, artwork.length) || 1 } as CSSProperties}>
        {artwork.map((item, index) => <span key={`${item.kind}:${item.value}`} className={`profile-favorite-art profile-favorites-${item.kind === 'driver' ? 'portraits' : 'teams'}`} style={{ '--favorite-turn': `${[0, -9, 3, 8, -3, -6][index % 6]}deg`, '--favorite-shift': `${[8, -12, 18, -8, -16, 14][index % 6]}px` } as CSSProperties}>
          {item.kind === 'driver' ? <DriverPortrait code={item.value} name={drivers[item.value] || item.value} season={season} /> : <TeamLogo name={item.value} id={teams[item.value]} season={season} size={150} />}
        </span>)}
      </div>
    </div>
    <div className="profile-favorites-heading"><h2 id="profile-favorites-title">Избранное</h2>{owner && <Link to="/favorites">Изменить избранное →</Link>}</div>
    <p className="profile-muted">{owner ? 'За кем ты следишь в мире гонок.' : 'За кем следит участник в мире гонок.'}</p>
    {!favorites.drivers.length && !favorites.teams.length ? <p className="profile-muted">{owner ? 'Добавь любимых пилотов и команды — они появятся здесь.' : 'Участник пока не выбрал любимых пилотов и команды.'}</p> : <div className="profile-following">
      <div><h3>Пилоты</h3>{favorites.drivers.length ? <ul>{favorites.drivers.map(code => <li key={code}><Link to={`/driver-details?code=${encodeURIComponent(code)}&season=${season}`}><DriverPortrait code={code} name={drivers[code] || code} season={season} /><span>{drivers[code] || code}</span></Link></li>)}</ul> : <p className="profile-muted">Пилоты не выбраны.</p>}</div>
      <div><h3>Команды</h3>{favorites.teams.length ? <ul>{favorites.teams.map(team => <li key={team}><Link to={teams[team] ? `/constructor-details?constructorId=${encodeURIComponent(teams[team])}&season=${season}` : '/constructors'}><TeamLogo name={team} id={teams[team]} season={season} /><span>{team}</span></Link></li>)}</ul> : <p className="profile-muted">Команды не выбраны.</p>}</div>
    </div>}
  </section>;
}
