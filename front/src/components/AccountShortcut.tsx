import { Link, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { apiRequest } from '../helpers/api';
import { avatarUrl, defaultAvatar, PROFILE_AVATAR_CHANGED_EVENT, type Avatar } from '../pages/profile/avatar';
import './account-shortcut.css';
import { HomeIcon } from '../pages/index/HomeIcon';

export function AccountShortcut() {
  const { loaded, signedIn } = useAuthState();
  const { pathname } = useLocation();
  const [avatar, setAvatar] = useState<Avatar | null>(null);
  const [failedSource, setFailedSource] = useState('');
  useEffect(() => {
    if (!loaded || !signedIn) return;
    let active = true;
    let generation = 0;
    const refresh = () => {
      const request = ++generation;
      setAvatar(null);
      setFailedSource('');
      void apiRequest<{ avatar?: Avatar }>('/api/profiles/me').then(profile => {
        if (active && request === generation) setAvatar(profile.avatar || defaultAvatar);
      }).catch(() => { /* The account link remains available if the avatar cannot load. */ });
    };
    const changed = (event: Event) => { generation += 1; setFailedSource(''); setAvatar((event as CustomEvent<Avatar>).detail); };
    refresh();
    window.addEventListener(AUTH_CHANGED_EVENT, refresh);
    window.addEventListener(PROFILE_AVATAR_CHANGED_EVENT, changed);
    return () => { active = false; window.removeEventListener(AUTH_CHANGED_EVENT, refresh); window.removeEventListener(PROFILE_AVATAR_CHANGED_EVENT, changed); };
  }, [loaded, signedIn]);
  const source = signedIn && avatar ? avatarUrl(avatar) : '';
  const label = !loaded ? 'Аккаунт' : signedIn ? 'Мой профиль' : 'Войти в аккаунт';
  const destination = signedIn ? '/profile' : '/account';
  const active = ['/profile', '/account', '/settings', '/favorites'].includes(pathname);

  return <Link to={destination} className="account-shortcut" aria-label={label} title={label} data-active={active || undefined} aria-current={pathname === destination ? 'page' : undefined}>
    {source && source !== failedSource ? <img className="account-shortcut-avatar" src={source} width="28" height="28" alt="" onError={() => setFailedSource(source)} /> : <HomeIcon name="account" />}
    <span>{!loaded ? 'Аккаунт' : signedIn ? 'Профиль' : 'Войти'}</span>
  </Link>;
}
