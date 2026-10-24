import { Link, useLocation } from 'react-router-dom';
import { HomeIcon } from '../pages/index/HomeIcon';
import './menu-shortcut.css';

export function MenuShortcut() {
  const { pathname, search } = useLocation();
  if (pathname === '/menu') return null;
  return <Link to="/menu" state={{ menuFrom: pathname + search }} className="menu-shortcut">
    <HomeIcon name="menu" /><span>Меню</span>
  </Link>;
}
