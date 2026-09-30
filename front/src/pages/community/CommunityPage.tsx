import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { useAuthState } from '../../helpers/auth';
import { BackButton } from '../../components/BackButton';
import './community.css';

type Weekly = {track_id: string; name: string; start: string; end: string; entries: {name: string; time_ms: number}[]};
type Mine = {referrals: {arrived: number; activated: number; returned: number}; badges: string[]; shares: {token: string; title: string; active: boolean}[]};
const time = (ms: number) => `${Math.floor(ms / 60000)}:${(ms / 1000 % 60).toFixed(3).padStart(6, '0')}`;
export default function CommunityPage() {
  const auth = useAuthState();
  const [weekly, setWeekly] = useState<Weekly | null>(null), [mine, setMine] = useState<Mine | null>(null);
  const [error, setError] = useState(''), [version, setVersion] = useState(0), [busy, setBusy] = useState('');
  useEffect(() => {
    let active = true;
    apiRequest<Weekly>('/api/engagement/weekly').then(data => {if (active) setWeekly(data);}).catch(() => {if (active) setError('Не удалось загрузить трассу недели.');});
    if (auth.signedIn) apiRequest<Mine>('/api/engagement/mine').then(data => {if (active) setMine(data);}).catch(() => {if (active) setError('Личный раздел временно недоступен.');});
    return () => {active = false;};
  }, [auth.signedIn, version]);
  async function revoke(token: string) {
    setBusy(token); setError('');
    try {await apiRequest(`/api/engagement/shares/${token}/revoke`, {}, 'POST'); setVersion(v => v + 1);}
    catch {setError('Не удалось отозвать ссылку.');}
    finally {setBusy('');}
  }
  return <main className="community-page"><BackButton>← Назад</BackButton><header><small>F1Hub · участвуем вместе</small><h1>С друзьями</h1><p>Соревнуйтесь по очкам и времени, делитесь своими результатами.</p></header>
    {error && <p role="alert">{error} <button onClick={() => {setError(''); setVersion(v => v + 1);}}>Повторить</button></p>}
    <div className="community-grid">
      <section className="community-card"><small>Каждую неделю — новый старт</small><h2>Трасса недели</h2>
        {!weekly ? <p role="status">Загружаем соревнование…</p> : <><h3>{weekly.name}</h3><p>До {new Date(weekly.end).toLocaleString('ru-RU', {day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit'})}. Граница недели — понедельник, 00:00 UTC.</p>
          <Link className="community-primary" to={`/race-game?track=${weekly.track_id}&weekly=1`}>Проехать три круга →</Link>
          <ol className="community-ranking">{weekly.entries.slice(0, 10).map((entry, i) => <li key={i}><span>{entry.name}</span><strong>{time(entry.time_ms)}</strong></li>)}</ol>
          {!weekly.entries.length && <p>Пока нет заездов — можно открыть таблицу первым.</p>}
          <small>Считаются сохранённые заезды этой недели. Постоянные рекорды не обнуляются.</small>
        </>}
      </section>
      <section className="community-card"><h2>Ваш следующий уик-энд</h2><p>Сохраните прогноз, а после гонки получите личный разбор и карточку результата.</p><Link className="community-primary" to="/predictions">Мой прогноз →</Link><p><Link to={auth.signedIn ? '/predictions?tab=leagues' : '/account?returnTo=leagues'}>Создать лигу или мини-чемпионат →</Link></p>{auth.signedIn && <><p><Link to="/predictions?tab=history">Мой сезон и разбор этапа →</Link></p><p><Link to="/settings">Выбрать напоминания →</Link></p></>}<small>Напоминания управляются вашими настройками. Ежедневных серий и штрафов за пропуски нет.</small></section>
    </div>
    {auth.loaded && !auth.signedIn && <p><Link to="/account?returnTo=community">Войдите</Link>, чтобы сохранять результаты и видеть достижения.</p>}
    {auth.signedIn && mine && <section className="community-card"><h2>Ваш вклад в сообщество</h2><div className="community-badges">{mine.badges.length ? mine.badges.map(badge => <span key={badge}>★ {badge}</span>) : <p>Пригласите участника в свою лигу или предложите другу побить ваше время — здесь появятся достижения.</p>}</div>
      <p>Новых участников по вашим приглашениям: {mine.referrals.arrived}. Сохранили первый прогноз или заезд: {mine.referrals.activated}. Вернулись с прогнозом другого этапа: {mine.referrals.returned}.</p><small>Считаем реальные сохранения, не открытия ссылки. Достижения не добавляют очков в прогнозах.</small>
      <details><summary>Последние публичные карточки ({mine.shares.length})</summary>{mine.shares.map(share => <div className="community-share-row" key={share.token}><span>{share.title}</span>{share.active ? <><Link to={`/share/${share.token}`}>Открыть</Link><button disabled={Boolean(busy)} onClick={() => void revoke(share.token)}>{busy === share.token ? 'Отзываем…' : 'Отозвать ссылку'}</button></> : <small>Истекла или недоступна</small>}</div>)}<small>Отзыв закрывает ссылку, но не удаляет уже отправленные сообщения и скачанные изображения.</small></details>
    </section>}
  </main>;
}
