import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { AUTH_CHANGED_EVENT, type AuthState } from '../../helpers/auth';
import { type PersonalPrediction } from './personal-summary';
import { formatTimezoneLabel } from '../../helpers/timezone';
import { PersonalDestinations } from './PersonalDestinations';
import { HomeIcon } from './HomeIcon';
import './personal-home.css';

function PersonalCards({ timezone, personalized }: { timezone: string; personalized: boolean }) {
  const [prediction, setPrediction] = useState<PersonalPrediction | null>(null);
  const [failed, setFailed] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const lastRefresh = useRef(0);
  useEffect(() => {
    let active = true;
    lastRefresh.current = Date.now();
    void apiRequest<PersonalPrediction>('/api/predictions/current').then(value => {
      if (!active) return;
      setPrediction(value); setFailed([]);
      setLoaded(true);
    }).catch(() => {
      if (!active) return;
      setPrediction(null); setFailed(['прогноз']);
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
  const deadline = Date.parse(prediction?.deadline_utc || '');
  const reload = () => { setLoaded(false); setRefresh(v => v + 1); };
  return <>
    {failed.length > 0 && <p className="personal-home-error" role="status">Не загрузились: {failed.join(', ')}. <button type="button" onClick={reload} disabled={!loaded}>Повторить</button></p>}
    <details className="personal-home-details">
      <summary>Личные разделы <HomeIcon name="chevronDown" /></summary>
      <div className="personal-home-more">
        {prediction?.event_name && <p className="personal-home-event">{prediction.event_name}</p>}
        {prediction && Number.isFinite(deadline) && <dl className="personal-home-facts"><div><dt>Приём прогнозов до</dt><dd><time dateTime={new Date(deadline).toISOString()}>{new Date(deadline).toLocaleString('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}</time><span>{formatTimezoneLabel(timezone)}</span></dd></div></dl>}
        <PersonalDestinations personalized={personalized} />
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
