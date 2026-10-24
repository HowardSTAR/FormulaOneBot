import { useEffect } from 'react';
import { useHeroData } from '../../context/useHeroData';
import { useAuthState } from '../../helpers/auth';
import { useMediaQuery } from '../../helpers/useMediaQuery';
import { useHomeSection } from './home-section-model';
import { HomeShowcase } from './HomeShowcase';
import { HomeSectionContent } from './HomeSections';
import { WeekendBoard } from './WeekendBoard';
import { HomeStandings } from './HomeStandings';
import { HomeShortcuts } from './HomeShortcuts';
import { PersonalHome } from './PersonalHome';
import './home.css';
import './home-controls.css';
import './home-desktop.css';

export type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';

export default function IndexPage() {
  const { nextRace, schedule, userTz, loaded, load } = useHeroData();
  const auth = useAuthState();
  const overview = useMediaQuery('(min-width: 1200px)');
  const section = useHomeSection();
  const season = nextRace?.season || new Date().getFullYear();
  useEffect(() => { if (!loaded) void load(); }, [loaded, load]);

  return <main className="home-screen" data-overview={overview || undefined} data-section={section} data-account={auth.signedIn ? 'member' : 'guest'} id="home-content" tabIndex={-1}>
    <h1 className="home-sr-only">{section === 'season' ? 'Формула-1' : section === 'games' ? 'Игры' : section === 'guide' ? 'Справка и отзывы' : 'Подписка'}</h1>
    <HomeShowcase season={season} section={section} />
    {section === 'season' ? <>
    <div className="home-weekend">
      <WeekendBoard race={nextRace} sessions={schedule} timezone={userTz} loaded={loaded} onRetry={() => void load()} />
    </div>
    <HomeStandings season={season} />
    <div className="home-personal-column">
      {auth.signedIn && <PersonalHome auth={auth} timezone={userTz} />}
      <HomeShortcuts />
    </div>
    </> : <HomeSectionContent section={section} />}
  </main>;
}
