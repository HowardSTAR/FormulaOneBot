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
    <span className="app-header-link-icon"><IndexIcon name={item.icon} /></span><span className="app-header-link-label">{item.label}</span><span className="app-header-link-arrow" aria-hidden>›</span>
  </Link>;
}

function SidebarAccordion({ group, pathname }: { group: NavigationGroup; pathname: string }) {
  const active = group.items.some(item => navigationActive(item, pathname));
  const [open, setOpen] = useState(active);
  const expanded = open || active;
  const id = `app-header-${group.id}-menu`;
  return <div className={`app-header-menu${expanded ? ' is-open' : ''}${active ? ' active' : ''}`}>
    <button type="button" className={`app-header-link app-header-menu-trigger${active ? ' active' : ''}`} aria-expanded={expanded} aria-controls={id} onClick={() => setOpen(value => !value)}>
      <span className="app-header-link-icon"><IndexIcon name={group.icon} /></span><span className="app-header-link-label">{group.label}</span><span className="app-header-link-arrow" aria-hidden>›</span>
    </button>
    <div id={id} className="app-header-submenu" aria-hidden={!expanded}>
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
      <span className="app-header-nav-label">Навигация</span>
      {nav.primary.map(item => <SidebarLink key={item.to} item={item} pathname={pathname} />)}
      {nav.groups.slice(0, 3).map(group => <SidebarAccordion key={group.id} group={group} pathname={pathname} />)}
      {nav.general.map(item => <SidebarLink key={item.to} item={item} pathname={pathname} />)}
      <button type="button" className="app-header-link app-header-menu-trigger" onClick={startOnboarding}><span className="app-header-link-icon"><IndexIcon name="wiki" /></span><span className="app-header-link-label">Короткое знакомство</span></button>
      <SidebarAccordion group={nav.groups[3]} pathname={pathname} />
    </nav>
    <div className="app-header-bottom">
      {!!nav.personal.length && <nav className="app-header-nav app-header-nav-secondary" aria-label="Личные разделы и управление">{nav.personal.map(item => <SidebarLink key={item.to} item={item} pathname={pathname} />)}</nav>}
      {auth.loaded && !auth.signedIn && <div className="app-header-guest"><div><i aria-hidden />Гостевой режим</div><p>Календарь, результаты и статистика доступны без входа.</p></div>}
      <div className="app-header-status"><small>Неофициальные данные автоспорта</small></div>
    </div>
  </header>;
}
