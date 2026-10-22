import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useHeroData } from '../../context/useHeroData';
import { useAuthState } from '../../helpers/auth';
import { apiRequest } from '../../helpers/api';
import Hero from './Hero';
import { WeekendBoard, QuickAccess } from './WeekendBoard';
import { PersonalHome } from './PersonalHome';
import { HomeLinkList } from './HomeLinkList';
import { HomeIcon } from './HomeIcon';
import './home.css';

export type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';
type Standing = { position: number; name: string; points: number; constructorName?: string };
type StandingsState = { season: number; rows: Standing[]; failed: boolean };

function Standings({ title, to, state, season, retry }: {
  title: string; to: string; state: StandingsState | null; season: number; retry: () => void;
}) {
  const current = state?.season === season ? state : null;
  return <section className="home-standing home-panel" aria-label={`${title} · сезон ${season}`}>
    <header className="home-section-head"><h3>{title}</h3><Link to={`${to}?year=${season}`}>Весь зачёт <span aria-hidden="true">↗</span></Link></header>
    {!current ? <p className="home-empty" role="status">Загружаем зачёт…</p>
      : current.failed ? <div className="home-empty" role="status"><p>Не удалось загрузить зачёт.</p><button type="button" className="home-text-action" onClick={retry}>Повторить</button></div>
      : !current.rows.length ? <p className="home-empty">Очков пока нет. <Link to={`${to}?year=${season}`}>Открыть зачёт</Link></p>
      : <><div className="home-standing-labels" aria-hidden="true"><span>Позиция</span><span>Очки</span></div>
        <ol className="home-standing-list">{current.rows.map(row => <li key={`${row.position}-${row.name}`}>
          <span className="home-position" aria-label={`Место ${row.position}`}>{String(row.position).padStart(2, '0')}</span>
          <span className="home-entrant"><strong>{row.name}</strong>{row.constructorName && <small>{row.constructorName}</small>}</span>
          <span className="home-points" aria-label={`${row.points} очков`}>{row.points.toLocaleString('ru-RU')}</span>
        </li>)}</ol></>}
  </section>;
}

export default function IndexPage() {
  const { nextRace, schedule, userTz, loaded, load } = useHeroData();
  const auth = useAuthState();
  const season = nextRace?.season || new Date().getFullYear();
  const [drivers, setDrivers] = useState<StandingsState | null>(null);
  const [teams, setTeams] = useState<StandingsState | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => { if (!loaded) void load(); }, [loaded, load]);
  useEffect(() => {
    let active = true;
    const get = async (path: string, key: 'drivers' | 'constructors', set: (value: StandingsState) => void) => {
      try {
        const data = await apiRequest<{ drivers?: Standing[]; constructors?: Standing[] }>(path, { season });
        if (active) set({ season, rows: (data[key] || []).slice(0, 5), failed: false });
      } catch { if (active) set({ season, rows: [], failed: true }); }
    };
    void get('/api/drivers', 'drivers', setDrivers);
    void get('/api/constructors', 'constructors', setTeams);
    return () => { active = false; };
  }, [season, refresh]);
  const retryStandings = () => { setDrivers(null); setTeams(null); setRefresh(value => value + 1); };
  return <main className="home-screen" id="home-content" tabIndex={-1}>
    <header className="home-heading"><div><p className="home-eyebrow">Ваш гоночный уик-энд</p><h1>Обзор</h1></div><Link to="/season" className="home-season-link">Сезон {season} <span aria-hidden="true">↗</span></Link></header>
    <div className="home-weekend-grid"><div className="home-race-column">
      <Hero nextRace={nextRace} schedule={schedule} userTz={userTz} loaded={loaded} onRetry={() => void load()} />
      <PersonalHome auth={auth} timezone={userTz} />
    </div><WeekendBoard race={nextRace} sessions={schedule} timezone={userTz} loaded={loaded} /></div>
    <section className="home-championship" aria-labelledby="home-championship-title">
      <header className="home-section-head home-championship-head"><h2 id="home-championship-title">В борьбе за титул</h2><span>Зачёт {season}</span></header>
      <div className="home-standings-grid"><Standings title="Пилоты" to="/drivers" state={drivers} season={season} retry={retryStandings} /><Standings title="Команды" to="/constructors" state={teams} season={season} retry={retryStandings} /></div>
    </section>
    <QuickAccess />
    <details className="home-more"><summary><span>Вне трассы <small>Игры, история и сообщество</small></span><HomeIcon name="chevronDown" /></summary><HomeLinkList label="Ещё в TurboTears" items={[
      { to: '/reaction-game', label: 'Тест реакции', icon: 'reaction' }, { to: '/reflex-grid-game', label: 'Reflex Grid', icon: 'grid' },
      { to: '/race-game', label: 'Emerald Loop', icon: 'arcade' }, { to: '/history', label: 'История чемпионата', icon: 'history' }, { to: '/community', label: 'Сообщество', icon: 'social' },
    ]} /></details>
  </main>;
}
