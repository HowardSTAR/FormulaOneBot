import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuthState } from '../helpers/auth';
import { navigationFor, navigationActive, type NavigationGroup, type NavigationItem } from '../helpers/navigation';
import IndexIcon from '../pages/index/IndexIcon';
import './SidebarIcons.css';
import { startOnboarding } from '../helpers/onboarding';

function SidebarLink({ item, pathname }: { item: NavigationItem; pathname: string }) {
  const active = navigationActive(item, pathname);
  return <Link to={item.to} className={`app-header-link${active ? ' active' : ''}`} aria-current={active ? 'page' : undefined}>
    <span className="app-header-link-icon"><IndexIcon name={item.icon} /></span><span className="app-header-link-label">{item.label}</span>
  </Link>;
}

function SidebarAccordion({ group, pathname }: { group: NavigationGroup; pathname: string }) {
  const active = group.items.some(item => navigationActive(item, pathname));
  const [choice, setChoice] = useState<{ pathname: string; open: boolean } | null>(null);
  const expanded = choice?.pathname === pathname ? choice.open : active;
  const id = `app-header-${group.id}-menu`;
  return <div className={`app-header-menu${expanded ? ' is-open' : ''}${active ? ' active' : ''}`}>
    <button type="button" className={`app-header-link app-header-menu-trigger${active ? ' active' : ''}`} aria-expanded={expanded} aria-controls={id} onClick={() => setChoice({ pathname, open: !expanded })}>
      <span className="app-header-link-icon"><IndexIcon name={group.icon} /></span><span className="app-header-link-label">{group.label}</span><span className="app-header-link-arrow" aria-hidden>›</span>
    </button>
    <div id={id} className="app-header-submenu" aria-hidden={!expanded}>
      {expanded && group.actions?.map(action => <button key={action.id} type="button" className="app-header-submenu-link" onClick={startOnboarding}>
        <span className="app-header-submenu-icon" aria-hidden><IndexIcon name={action.icon} /></span>{action.label}
      </button>)}
      {expanded && group.items.map(item => { const selected = navigationActive(item, pathname); return <Link key={item.to} to={item.to} className={`app-header-submenu-link${selected ? ' active' : ''}`} aria-current={selected ? 'page' : undefined}>
        <span className="app-header-submenu-icon" aria-hidden><IndexIcon name={item.icon} /></span>{item.label}
      </Link>; })}
    </div>
  </div>;
}

export function AppHeader() {
  const auth = useAuthState();
  const { pathname } = useLocation();
  const nav = navigationFor(auth);
  return <header className="app-header">
    <div className="app-header-brand-wrap"><Link to="/" className="app-header-brand" aria-label="TurboTears — главная"><span className="app-header-brand-accent">Turbo</span><span>Tears</span></Link><span className="app-header-brand-caption">Race intelligence</span></div>
    <nav className="app-header-nav" aria-label="Главное меню">
      {nav.sections.map(section => <section key={section.id} className="app-header-section" aria-labelledby={`app-header-section-${section.id}`}>
        <h2 id={`app-header-section-${section.id}`} className="app-header-section-label">{section.label}</h2>
        {section.items.map(entry => 'to' in entry ? <SidebarLink key={entry.to} item={entry} pathname={pathname} /> : <SidebarAccordion key={entry.id} group={entry} pathname={pathname} />)}
      </section>)}
    </nav>
    <div className="app-header-bottom">
      {nav.management && <nav className="app-header-nav app-header-nav-secondary" aria-label="Управление"><SidebarAccordion group={nav.management} pathname={pathname} /></nav>}
      {auth.loaded && !auth.signedIn && <div className="app-header-guest"><div><i aria-hidden />Гостевой режим</div><p>Календарь, результаты и статистика доступны без входа.</p></div>}
      <div className="app-header-status"><small>Неофициальные данные автоспорта</small></div>
    </div>
  </header>;
}
