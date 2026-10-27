import { lazy, Suspense } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { BackButton } from '../../components/BackButton';
import { GlassSwitch } from '../index/GlassSwitch';
import '../index/home-controls.css';
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
  return <div className={`personal-hub${!account && !settings && !favorites ? ' personal-hub-profile' : ''}`}>
    <header className="personal-hub-header"><BackButton fallback="/" /><GlassSwitch
      className="personal-hub-switch" label="Личный раздел" selected={account || settings ? 'account' : 'profile'}
      items={[{ id: 'profile', label: 'Профиль', to: '/profile' }, { id: 'account', label: 'Аккаунт', to: '/account' }]} />
      <NavLink className="personal-hub-settings" to="/settings">Настройки</NavLink></header>
    <Suspense fallback={<p role="status">Загружаем личный раздел…</p>}>
      {account ? <Account embedded /> : settings ? <Settings embedded /> : favorites ? <Favorites embedded /> : <Profile embedded />}
    </Suspense>
  </div>;
}
