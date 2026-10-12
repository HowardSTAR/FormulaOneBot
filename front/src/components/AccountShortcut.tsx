import { Link, useLocation } from 'react-router-dom';
import { useAuthState } from '../helpers/auth';
import accountIcon from '../assets/navigation/account.png';
import './account-shortcut.css';

export function AccountShortcut() {
  const { loaded, signedIn } = useAuthState();
  const { pathname } = useLocation();
  const label = !loaded ? 'Аккаунт' : signedIn ? 'Мой профиль' : 'Войти в аккаунт';
  const destination = signedIn ? '/profile' : '/account';
  const active = ['/profile', '/account', '/settings', '/favorites'].includes(pathname);

  return <Link to={destination} className="account-shortcut" aria-label={label} title={label} data-active={active || undefined} aria-current={pathname === destination ? 'page' : undefined}>
    <img src={accountIcon} width="28" height="28" alt="" aria-hidden="true" />
    <span>{!loaded ? 'Аккаунт' : signedIn ? 'Профиль' : 'Войти'}</span>
  </Link>;
}
