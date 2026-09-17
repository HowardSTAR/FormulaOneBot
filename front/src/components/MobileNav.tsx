import { NavLink } from 'react-router-dom';
import './mobile-nav.css';

export function MobileNav() {
  return <nav className="mobile-primary-nav" aria-label="Основная навигация">
    <NavLink to="/" end>Главная</NavLink>
    <NavLink to="/next-race">Уик-энд</NavLink>
    <NavLink to="/predictions">Прогнозы</NavLink>
    <NavLink to="/account">Моё</NavLink>
  </nav>;
}
