import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuthState } from '../../helpers/auth';
import { navigationFor, type NavigationItem } from '../../helpers/navigation';
import { startOnboarding } from '../../helpers/onboarding';
import { HomeIcon } from '../index/HomeIcon';
import { LegalFooter } from '../../components/LegalFooter';
import './menu.css';

export default function MenuPage() {
  const auth = useAuthState();
  const nav = navigationFor(auth);
  const location = useLocation();
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);
  const links = (items: NavigationItem[]) => items.map(item => <li key={item.to}>
    <Link to={item.to === '/profile' && !auth.signedIn ? '/account' : item.to}>
      <HomeIcon name={item.icon} /><span>{item.to === '/' ? 'Главная' : item.label}</span><HomeIcon name="chevronRight" />
    </Link>
  </li>);

  return <main className="menu-page">
    <header className="menu-page-heading">
      <h1 ref={heading} tabIndex={-1}>Меню</h1>
      <button type="button" onClick={() => location.state?.menuFrom ? navigate(-1) : navigate('/')} aria-label="Назад из меню">Назад <span aria-hidden="true">←</span></button>
    </header>
    <nav className="menu-sections" aria-label="Все разделы сайта">
      <section><h2>Главное</h2><ul>{links(nav.primary)}</ul></section>
      {nav.groups.map(group => <section key={group.id}><h2>{group.label}</h2><ul>{links(group.items)}</ul></section>)}
      <section><h2>Справка и аккаунт</h2><ul>{links(nav.general)}<li><button type="button" onClick={startOnboarding}><HomeIcon name="wiki" /><span>Короткое знакомство</span><HomeIcon name="chevronRight" /></button></li></ul></section>
      {!!nav.personal.length && <section><h2>Личные разделы и управление</h2><ul>{links(nav.personal)}</ul></section>}
    </nav>
    <details className="menu-project"><summary>О проекте и документы <HomeIcon name="chevronDown" /></summary><LegalFooter /></details>
  </main>;
}
