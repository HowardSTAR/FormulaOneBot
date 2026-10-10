import { lazy, Suspense } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { BackButton } from '../../components/BackButton';
import './personal-hub.css';

const Account = lazy(() => import('./AccountPage'));
const Profile = lazy(() => import('../profile/ProfilePage'));
const Settings = lazy(() => import('../settings/SettingsPage'));
const Favorites = lazy(() => import('../favorites/FavoritesPage'));

export default function PersonalHub() {
  const pathname = useLocation().pathname;
  const account = pathname === '/account';
  const settings = pathname === '/settings';
  const favorites = pathname === '/favorites';
  return <div className="personal-hub">
    <header className="personal-hub-header"><BackButton fallback="/" /><nav className={`personal-hub-switch${account || settings ? ' personal-hub-switch-account' : ''}`} aria-label="Личный раздел">
      <span className="personal-hub-slider" aria-hidden="true" />
      <NavLink to="/profile" className={() => !account && !settings ? 'active' : ''} aria-current={favorites ? 'page' : undefined}>Профиль</NavLink>
      <NavLink to="/account" className={() => account || settings ? 'active' : ''}>Аккаунт</NavLink>
    </nav><NavLink className="personal-hub-settings" to="/settings">Настройки</NavLink></header>
    <Suspense fallback={<p role="status">Загружаем личный раздел…</p>}>
      {account ? <Account embedded /> : settings ? <Settings embedded /> : favorites ? <Favorites embedded /> : <Profile embedded />}
    </Suspense>
  </div>;
}
