import { lazy, Suspense } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { BackButton } from '../../components/BackButton';
import './personal-hub.css';

const Account = lazy(() => import('./AccountPage'));
const Profile = lazy(() => import('../profile/ProfilePage'));

export default function PersonalHub() {
  const account = useLocation().pathname === '/account';
  return <div className="personal-hub">
    <header className="personal-hub-header"><BackButton fallback="/" /><nav className="personal-hub-switch" aria-label="Личный раздел">
      <NavLink to="/profile">Профиль</NavLink><NavLink to="/account">Аккаунт</NavLink>
    </nav></header>
    <Suspense fallback={<p role="status">Загружаем личный раздел…</p>}>
      {account ? <Account embedded /> : <Profile embedded />}
    </Suspense>
  </div>;
}
