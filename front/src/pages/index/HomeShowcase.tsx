import { HomeSpotlight } from './HomeSpotlight';
import { HomeSections, HomeSectionHero } from './HomeSections';
import type { HomeSection } from './home-section-model';
import './home-showcase.css';

/** One intrinsic grid row keeps navigation stable, including at larger text sizes. */
export function HomeShowcase({ season, section }: { season: number; section: HomeSection }) {
  return <div className="home-showcase">
    <div className="home-banner-stage">
      <div className="home-banner-panel" data-active={section === 'season' || undefined} inert={section !== 'season'} aria-hidden={section !== 'season' || undefined}><HomeSpotlight season={season} /></div>
      {(['games', 'guide', 'subscription'] as const).map(view => <div className="home-banner-panel" key={view} data-active={section === view || undefined} inert={section !== view} aria-hidden={section !== view || undefined}><HomeSectionHero section={view} /></div>)}
    </div>
    <HomeSections />
  </div>;
}
