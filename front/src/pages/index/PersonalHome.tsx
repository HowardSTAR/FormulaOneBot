import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { AUTH_CHANGED_EVENT, type AuthState } from '../../helpers/auth';
import { predictionSummary, type PersonalPrediction } from './personal-summary';
import './personal-home.css';

function PersonalCards({ timezone, personalized }: { timezone: string; personalized: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [prediction, setPrediction] = useState<PersonalPrediction | null>(null);
  const [unread, setUnread] = useState<number | null>(null);
  const [failed, setFailed] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    let active = true;
    void Promise.allSettled([
      apiRequest<PersonalPrediction>('/api/predictions/current'),
      apiRequest<{ unread: number }>('/api/web-notifications/unread-count'),
    ]).then(([p, n]) => {
      if (!active) return;
      setPrediction(p.status === 'fulfilled' ? p.value : null);
      setUnread(n.status === 'fulfilled' ? n.value.unread : null);
      setFailed([...(p.status === 'rejected' ? ['прогноз'] : []), ...(n.status === 'rejected' ? ['уведомления'] : [])]);
      setLoaded(true);
    });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    const update = () => { setNow(Date.now()); setRefresh(v => v + 1); };
    window.addEventListener('focus', update);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', update); };
  }, []);
  const view = prediction ? predictionSummary(prediction, now) : null;
  const deadline = Date.parse(prediction?.deadline_utc || '');
  return <>
    <div className="personal-home-row">
      <Link to={prediction?.prediction?.points != null ? '/predictions?tab=leaderboard' : '/predictions'} className={`personal-home-prediction${view?.urgent ? ' personal-home-urgent' : ''}`}>
        <strong>Мой прогноз <span aria-hidden="true">→</span></strong>
        <span>{view?.title || (loaded ? 'Статус недоступен' : 'Проверяем…')}</span>
        {view?.urgent && <small>До закрытия меньше 2 часов</small>}
      </Link>
      <Link className="personal-home-inbox" to="/notifications" aria-label={unread === null ? 'Уведомления: количество неизвестно' : `Уведомления: непрочитанных ${unread}`} title={unread === 0 ? 'Всё прочитано' : 'Уведомления'}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
        <span>{unread === null ? '—' : unread > 99 ? '99+' : unread}</span>
      </Link>
      <button className="personal-home-toggle" aria-expanded={expanded} aria-controls="personal-home-more" onClick={() => setExpanded(v => !v)}>Ещё <span aria-hidden="true">{expanded ? '−' : '+'}</span></button>
    </div>
    {failed.length > 0 && <p className="personal-home-error" role="status">Не загрузились: {failed.join(', ')}. <button onClick={() => setRefresh(v => v + 1)}>Повторить</button></p>}
    {expanded && <div className="personal-home-more" id="personal-home-more">
      {prediction?.event_name && <p>{prediction.event_name}</p>}
      {prediction && Number.isFinite(deadline) && <p>Закрытие: {new Date(deadline).toLocaleString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })} · {timezone}</p>}
      <nav aria-label="Личные разделы">
        <Link to="/account">Аккаунт</Link><Link to="/settings">Напоминания</Link>
        {personalized && <Link to="/favorites">Избранное</Link>}
        <Link to="/predictions?tab=leaderboard">Мои результаты</Link>
        <button onClick={() => setRefresh(v => v + 1)}>Обновить</button>
      </nav>
    </div>}
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
    {auth.signedIn ? <PersonalCards key={identityVersion} timezone={timezone} personalized={auth.personalized} /> : <div className="personal-home-guest"><span>Ваши прогнозы и уведомления</span><Link to="/account">Войти →</Link></div>}
  </section>;
}
