import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { AUTH_CHANGED_EVENT, type AuthState } from '../../helpers/auth';
import { predictionSummary, type PersonalPrediction } from './personal-summary';
import { formatTimezoneLabel } from '../../helpers/timezone';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import { HomeLinkList } from './HomeLinkList';
import { HomeIcon } from './HomeIcon';
import './personal-home.css';

function PersonalCards({ timezone, personalized }: { timezone: string; personalized: boolean }) {
  const [prediction, setPrediction] = useState<PersonalPrediction | null>(null);
  const [latest, setLatest] = useState<{points: number | null; season: number; round: number; items?: {status: string}[]} | null>(null);
  const [unread, setUnread] = useState<number | null>(null);
  const [failed, setFailed] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const now = useVisibleClock(30000);
  const lastRefresh = useRef(0);
  useEffect(() => {
    let active = true;
    lastRefresh.current = Date.now();
    void Promise.allSettled([
      apiRequest<PersonalPrediction>('/api/predictions/current'),
      apiRequest<{ unread: number }>('/api/web-notifications/unread-count'),
      apiRequest<{latest: {points: number | null; season: number; round: number; items?: {status: string}[]} | null}>('/api/predictions/personal-season'),
    ]).then(([p, n, h]) => {
      if (!active) return;
      setPrediction(p.status === 'fulfilled' ? p.value : null);
      setUnread(n.status === 'fulfilled' ? n.value.unread : null);
      setLatest(h.status === 'fulfilled' ? h.value.latest : null);
      setFailed([...(p.status === 'rejected' ? ['прогноз'] : []), ...(n.status === 'rejected' ? ['уведомления'] : []), ...(h.status === 'rejected' ? ['результаты'] : [])]);
      setLoaded(true);
    });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    const update = () => {
      if (!document.hidden && Date.now() - lastRefresh.current >= 60000) setRefresh(v => v + 1);
    };
    window.addEventListener('focus', update);
    document.addEventListener('visibilitychange', update);
    return () => { window.removeEventListener('focus', update); document.removeEventListener('visibilitychange', update); };
  }, []);
  const view = prediction ? predictionSummary(prediction, now) : null;
  const showRecap = !prediction?.is_open && latest?.points != null && (
    prediction?.status !== 'ok' || now < Date.parse(prediction?.opens_at_utc || '') ||
    (latest.season === prediction?.season && latest.round === prediction?.round)
  );
  const deadline = Date.parse(prediction?.deadline_utc || '');
  const reload = () => { setLoaded(false); setRefresh(v => v + 1); };
  return <>
    <div className="personal-home-row">
      <Link to={showRecap || prediction?.prediction?.points != null ? '/predictions?tab=history' : '/predictions'} className={`personal-home-prediction${view?.urgent ? ' personal-home-urgent' : ''}`}>
        <strong>{showRecap ? 'Разобрать мой этап' : view?.action || 'Мой прогноз'} <span aria-hidden="true">→</span></strong>
        <span>{showRecap ? `Последний результат: ${latest?.points} очк.${latest?.items?.some(item => item.status === 'unavailable') ? ' · предварительно' : ''}` : view?.title || (loaded ? 'Статус недоступен' : 'Проверяем…')}</span>
        {view?.urgent && <small>До закрытия меньше 2 часов</small>}
      </Link>
      <Link className="personal-home-inbox" to="/notifications" aria-label={unread === null ? 'Уведомления: количество неизвестно' : `Уведомления: непрочитанных ${unread}`} title={unread === 0 ? 'Всё прочитано' : 'Уведомления'}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
        <span>{unread === null ? '—' : unread > 99 ? '99+' : unread}</span>
      </Link>
    </div>
    {failed.length > 0 && <p className="personal-home-error" role="status">Не загрузились: {failed.join(', ')}. <button type="button" onClick={reload} disabled={!loaded}>Повторить</button></p>}
    <details className="personal-home-details">
      <summary>Личные разделы <HomeIcon name="chevronDown" /></summary>
      <div className="personal-home-more">
        {prediction?.event_name && <p className="personal-home-event">{prediction.event_name}</p>}
        {prediction && Number.isFinite(deadline) && <dl className="personal-home-facts"><div><dt>Приём прогнозов до</dt><dd><time dateTime={new Date(deadline).toISOString()}>{new Date(deadline).toLocaleString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}</time><span>{formatTimezoneLabel(timezone)}</span></dd></div></dl>}
        <HomeLinkList label="Личные разделы" items={[
          { to: '/account', label: 'Аккаунт', icon: 'account' }, { to: '/settings', label: 'Напоминания', icon: 'notifications' },
          ...(personalized ? [{ to: '/favorites', label: 'Избранное', icon: 'favorite' } as const] : []),
          { to: '/predictions?tab=history', label: 'Результаты прогнозов', icon: 'results' }, { to: '/community', label: 'С друзьями · трасса недели', icon: 'social' },
        ]} />
        <button type="button" className="personal-home-refresh" onClick={reload} disabled={!loaded}><HomeIcon name="refresh" />{loaded ? 'Обновить данные' : 'Обновляем…'}</button>
      </div>
    </details>
  </>;
}

export function PersonalHome({ auth, timezone }: { auth: AuthState; timezone: string }) {
  const [identityVersion, setIdentityVersion] = useState(0);
  useEffect(() => {
    const reset = () => setIdentityVersion(v => v + 1);
    window.addEventListener(AUTH_CHANGED_EVENT, reset);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, reset);
  }, []);
  if (!auth.loaded) return <section className="personal-home" aria-busy="true"><p>Загружаем личный раздел…</p></section>;
  return <section className="personal-home" aria-label="Мой уик-энд">
    {auth.signedIn ? <PersonalCards key={identityVersion} timezone={timezone} personalized={auth.personalized} /> : <div className="personal-home-guest"><span>Ваш прогноз на следующий этап</span><Link to="/predictions">Попробовать →</Link></div>}
  </section>;
}
