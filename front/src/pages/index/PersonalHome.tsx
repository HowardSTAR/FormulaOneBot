import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { AUTH_CHANGED_EVENT, type AuthState } from '../../helpers/auth';
import { predictionSummary, type PersonalPrediction } from './personal-summary';
import './personal-home.css';

function PersonalCards({ timezone }: { timezone: string }) {
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
    <button onClick={() => setRefresh(v => v + 1)} aria-label="Обновить данные моего уик-энда">Обновить данные</button>
    {!loaded && <p role="status">Загружаем ваши данные…</p>}
    {failed.length > 0 && <p role="status">Не удалось загрузить: {failed.join(', ')}. <button onClick={() => setRefresh(v => v + 1)}>Повторить</button></p>}
    <div className="personal-home-cards">
      <Link to={prediction?.prediction?.points != null ? '/predictions?tab=leaderboard' : '/predictions'} className={view?.urgent ? 'personal-home-urgent' : ''}>
        <small>{prediction?.event_name || 'Мой прогноз'}</small>
        <strong>{view?.title || (loaded ? 'Проверьте прогноз на странице' : 'Проверяем прогноз…')}</strong>
        {prediction && Number.isFinite(deadline) && <span>Закрытие: {new Date(deadline).toLocaleString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })} · {timezone}</span>}
        {view?.urgent && <span>Осталось меньше двух часов</span>}
        <b>{view?.action || 'Открыть прогнозы'} →</b>
      </Link>
      <Link to="/notifications"><small>Мои уведомления</small><strong>{unread === null ? 'Открыть уведомления' : unread === 0 ? 'Всё прочитано' : `Непрочитанных: ${unread}`}</strong><span>Сообщения сайта и результаты</span><b>Перейти →</b></Link>
    </div>
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
    <header><div><small>Всё важное под рукой</small><h2>{auth.signedIn ? 'Мой уик-энд' : 'Ваш уик-энд Formula 1'}</h2></div><Link to="/account">{auth.signedIn ? 'Мой аккаунт' : 'Войти'} →</Link></header>
    {auth.signedIn ? <PersonalCards key={identityVersion} timezone={timezone} /> : <p>Войдите, чтобы видеть свой прогноз и непрочитанные уведомления. Расписание и результаты доступны без входа.</p>}
    <nav aria-label="Быстрые действия">
      <Link to="/next-race">Расписание</Link>
      {auth.signedIn && <Link to="/settings">Напоминания</Link>}
      {auth.personalized && <Link to="/favorites">Мои пилоты и команды</Link>}
      {auth.signedIn && <Link to="/predictions?tab=leaderboard">Мои результаты</Link>}
    </nav>
  </section>;
}
