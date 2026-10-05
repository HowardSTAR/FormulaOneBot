import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuthState } from '../helpers/auth';
import { navigationFor, navigationActive, type NavigationItem } from '../helpers/navigation';
import IndexIcon from '../pages/index/IndexIcon';
import './mobile-nav.css';
import { primaryNavigationIndex, preparePageMotion } from '../helpers/pageMotion';

export function MobileNav() {
  const { pathname } = useLocation();
  const auth = useAuthState();
  const nav = navigationFor(auth);
  const dialog = useRef<HTMLDialogElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => {
    const node = dialog.current;
    if (!node?.open || node.dataset.phase === 'closing') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { node.close(); return; }
    node.dataset.phase = 'closing';
    // Also finish if an animation is interrupted by a resize or a media change.
    closeTimer.current = window.setTimeout(() => node.close(), 240);
  }, []);
  useEffect(() => { close(); }, [pathname, close]);
  useEffect(() => () => window.clearTimeout(closeTimer.current), []);
  useEffect(() => {
    const resized = () => { if (window.innerWidth > 767) dialog.current?.close(); };
    window.addEventListener('resize', resized);
    return () => window.removeEventListener('resize', resized);
  }, []);
  const activeIndex = open ? 4 : primaryNavigationIndex(pathname);
  const items = [
    { to: '/', label: 'Главная' },
    { to: '/next-race', label: 'Уик-энд' },
    { to: '/predictions', label: 'Прогнозы' },
    { to: '/account', label: 'Моё' },
  ];
  const links = (entries: NavigationItem[]) => entries.map(item => {
    const active = navigationActive(item, pathname);
    return <Link key={item.to} to={item.to} onClick={() => { preparePageMotion(pathname, item.to); close(); }} className={active ? 'active' : undefined} aria-current={active ? 'page' : undefined}><IndexIcon name={item.icon} /><span>{item.label}</span></Link>;
  });
  return <>
    <nav className="mobile-primary-nav" aria-label="Основная навигация" style={{ '--active-tab': activeIndex } as CSSProperties}>
      <span className="mobile-nav-indicator" aria-hidden="true" />
      {items.map((item, index) => <Link key={item.to} to={item.to} onClick={() => { preparePageMotion(pathname, item.to); close(); }} className={activeIndex === index ? 'active' : undefined} aria-current={primaryNavigationIndex(pathname) === index ? 'page' : undefined}>{item.label}</Link>)}
      <button type="button" className={activeIndex === 4 ? 'active' : undefined} aria-expanded={open} aria-controls="mobile-full-menu" onClick={() => { dialog.current?.showModal(); setOpen(true); }}>Меню</button>
    </nav>
    <dialog id="mobile-full-menu" className="mobile-menu-dialog" ref={dialog} aria-labelledby="mobile-menu-title" onClose={() => { window.clearTimeout(closeTimer.current); if (dialog.current) delete dialog.current.dataset.phase; setOpen(false); }} onCancel={event => { event.preventDefault(); close(); }} onAnimationEnd={event => { if (event.target === dialog.current && event.animationName === 'mobile-menu-out') dialog.current?.close(); }} onClick={event => { if (event.target === dialog.current) close(); }}>
      <div className="mobile-menu-content">
        <header><h2 id="mobile-menu-title">Все разделы</h2><button type="button" onClick={close} aria-label="Закрыть меню" autoFocus>×</button></header>
        {!auth.signedIn && <p className="mobile-menu-hint"><Link to="/account" onClick={close}>Войти в аккаунт →</Link> Личные разделы появятся после входа.</p>}
        <nav aria-label="Все разделы сайта">{open && <>
          <section><h3>Главное</h3><div>{links(nav.primary)}</div></section>
          {nav.groups.map(group => <section key={group.id}><h3>{group.label}</h3><div>{links(group.items)}</div></section>)}
          <section><h3>Справка и аккаунт</h3><div>{links(nav.general)}</div></section>
          {!!nav.personal.length && <section><h3>Личные разделы и управление</h3><div>{links(nav.personal)}</div></section>}
        </>}</nav>
      </div>
    </dialog>
  </>;
}
