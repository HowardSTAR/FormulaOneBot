import { Link, useLocation } from 'react-router-dom';
import './mobile-nav.css';

export function MobileNav() {
  const {pathname} = useLocation();
  const items = [
    {to: '/', label: 'Главная', active: pathname === '/'},
    {to: '/next-race', label: 'Уик-энд', active: ['/next-race', '/season', '/race-details', '/race-results', '/quali-results', '/sprint-results', '/sprint-quali-results'].includes(pathname)},
    {to: '/predictions', label: 'Прогнозы', active: pathname === '/predictions'},
    {to: '/account', label: 'Моё', active: ['/account', '/settings', '/favorites', '/notifications'].some(path => pathname === path || pathname.startsWith(`${path}/`))},
  ];
  return <nav className="mobile-primary-nav" aria-label="Основная навигация">
    {items.map(item => <Link key={item.to} to={item.to} className={item.active ? 'active' : undefined} aria-current={item.active ? 'page' : undefined}>{item.label}</Link>)}
  </nav>;
}
