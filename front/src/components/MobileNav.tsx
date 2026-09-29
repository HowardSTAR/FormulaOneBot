import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuthState } from '../helpers/auth';
import { navigationFor, navigationActive, type NavigationItem } from '../helpers/navigation';
import IndexIcon from '../pages/index/IndexIcon';
import './mobile-nav.css';

export function MobileNav() {
  const { pathname } = useLocation();
  const auth = useAuthState();
  const nav = navigationFor(auth);
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => { dialog.current?.close(); }, [pathname]);
  useEffect(() => {
    const resized = () => { if (window.innerWidth > 767) dialog.current?.close(); };
    window.addEventListener('resize', resized);
    return () => window.removeEventListener('resize', resized);
  }, []);
  const items = [
    { to: '/', label: 'Главная', active: pathname === '/' },
    { to: '/next-race', label: 'Уик-энд', active: ['/next-race', '/season', '/race-details', '/practice-results', '/race-results', '/quali-results', '/sprint-results', '/sprint-quali-results'].includes(pathname) },
    { to: '/predictions', label: 'Прогнозы', active: pathname === '/predictions' },
    { to: '/account', label: 'Моё', active: ['/account', '/settings', '/favorites', '/notifications'].includes(pathname) },
  ];
  const close = () => { dialog.current?.close(); setOpen(false); };
  const links = (entries: NavigationItem[]) => entries.map(item => {
    const active = navigationActive(item, pathname);
    return <Link key={item.to} to={item.to} onClick={close} className={active ? 'active' : undefined} aria-current={active ? 'page' : undefined}><IndexIcon name={item.icon} /><span>{item.label}</span></Link>;
  });
  return <>
    <nav className="mobile-primary-nav" aria-label="Основная навигация">
      {items.map(item => <Link key={item.to} to={item.to} onClick={close} className={item.active ? 'active' : undefined} aria-current={item.active ? 'page' : undefined}>{item.label}</Link>)}
      <button type="button" className={open || !items.some(item => item.active) ? 'active' : undefined} aria-expanded={open} aria-controls="mobile-full-menu" onClick={() => { dialog.current?.showModal(); setOpen(true); }}>Меню</button>
    </nav>
    <dialog id="mobile-full-menu" className="mobile-menu-dialog" ref={dialog} aria-labelledby="mobile-menu-title" onClose={() => setOpen(false)} onClick={event => { if (event.target === dialog.current) close(); }}>
      <div className="mobile-menu-content">
        <header><h2 id="mobile-menu-title">Все разделы</h2><button type="button" onClick={close} aria-label="Закрыть меню" autoFocus>×</button></header>
        {!auth.signedIn && <p className="mobile-menu-hint"><Link to="/account" onClick={close}>Войти в аккаунт →</Link> Личные разделы появятся после входа.</p>}
        <nav aria-label="Все разделы сайта">
          <section><h3>Главное</h3><div>{links(nav.primary)}</div></section>
          {nav.groups.map(group => <section key={group.id}><h3>{group.label}</h3><div>{links(group.items)}</div></section>)}
          <section><h3>Справка и аккаунт</h3><div>{links(nav.general)}</div></section>
          {!!nav.personal.length && <section><h3>Личные разделы и управление</h3><div>{links(nav.personal)}</div></section>}
        </nav>
      </div>
    </dialog>
  </>;
}
