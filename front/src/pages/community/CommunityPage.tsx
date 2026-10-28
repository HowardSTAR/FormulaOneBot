import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { useAuthState } from '../../helpers/auth';
import { HomeIcon, type HomeIconName } from '../index/HomeIcon';
import AvatarPortrait from '../profile/AvatarPortrait';
import { CommunityTrackPreview } from './CommunityTrackPreview';
import { useVisibleClock } from '../../helpers/useVisibleClock';
import type { WeeklyReminder } from '../../helpers/visitReminders';
import { communityTrackImage } from './communityTracks';
import './community.css';

type Weekly = { track_id: string; name: string; start: string; end: string; entries: { name: string; time_ms: number }[] };
type Mine = { referrals: { arrived: number; activated: number; returned: number }; badges: string[]; shares: { token: string; title: string; active: boolean }[] };
type League = { id: number; name: string; mode: 'season' | 'cup'; season: number | null };
type Result<T> = { data?: T; error?: string };
const time = (ms: number) => `${Math.floor(ms / 60000)}:${(ms / 1000 % 60).toFixed(3).padStart(6, '0')}`;

function CommunityLink({ to, icon, children }: { to: string; icon: HomeIconName; children: React.ReactNode }) {
  return <Link className="community-destination" to={to}><HomeIcon name={icon} /><span>{children}</span><HomeIcon name="chevronRight" /></Link>;
}

function Ranking({ entries, winners = false, limit = 10 }: { entries: Weekly['entries']; winners?: boolean; limit?: number }) {
  if (!entries.length) return <p className="community-empty">{winners ? 'Сохранённых заездов не было — победителя нет.' : 'Пока нет заездов — можно открыть таблицу первым.'}</p>;
  return <ol className="community-ranking" role="list">{entries.slice(0, limit).map((entry, i) => <li key={i}>
    <span className="community-place" aria-label={`Место ${entries.findIndex(candidate => candidate.time_ms === entry.time_ms) + 1}`}>{entries.findIndex(candidate => candidate.time_ms === entry.time_ms) + 1}</span><span>{winners && entry.time_ms === entries[0].time_ms && <span aria-label="Победитель">🏆 </span>}{entry.name}</span><strong>{time(entry.time_ms)}</strong>
  </li>)}</ol>;
}

export default function CommunityPage() {
  const auth = useAuthState();
  const [search] = useSearchParams();
  const now = useVisibleClock(60000);
  const [showAll, setShowAll] = useState(false);
  const [paceResult, setPaceResult] = useState<Result<WeeklyReminder | null>>({});
  const [leaguesResult, setLeaguesResult] = useState<Result<League[]>>({});
  const previousWeek = search.get('week');
  const [weeklyResult, setWeeklyResult] = useState<Result<Weekly>>({});
  const [mineResult, setMineResult] = useState<Result<Mine>>({});
  const [previousResult, setPreviousResult] = useState<Result<Weekly>>({});
  const [showPrevious, setShowPrevious] = useState(search.get('weekly') === 'previous');
  const [version, setVersion] = useState(0), [busy, setBusy] = useState(''), [error, setError] = useState('');
  const weekly = weeklyResult.data, mine = mineResult.data, previous = previousResult.data;
  useEffect(() => {
    let active = true;
    apiRequest<Weekly>('/api/engagement/weekly').then(data => { if (active) setWeeklyResult({ data }); }).catch(() => { if (active) setWeeklyResult({ error: 'Не удалось загрузить трассу недели.' }); });
    if (auth.signedIn) {
      apiRequest<{ weekly: WeeklyReminder | null }>('/api/engagement/weekly/me').then(data => { if (active) setPaceResult({ data: data.weekly }); }).catch(() => { if (active) setPaceResult({ error: 'Не удалось загрузить ваше время.' }); });
      apiRequest<{ leagues: League[] }>('/api/predictions/leagues').then(data => { if (active) setLeaguesResult({ data: data.leagues }); }).catch(() => { if (active) setLeaguesResult({ error: 'Не удалось загрузить ваши лиги.' }); });
      apiRequest<Mine>('/api/engagement/mine').then(data => { if (active) setMineResult({ data }); }).catch(() => { if (active) setMineResult({ error: 'Личный раздел временно недоступен.' }); });
    }
    return () => { active = false; };
  }, [auth.signedIn, version]);
  useEffect(() => {
    if (!weekly) return;
    const remaining = Date.parse(weekly.end) - Date.now();
    if (!Number.isFinite(remaining) || remaining <= 0) return;
    const timer = window.setTimeout(() => setVersion(value => value + 1), Math.min(remaining, 2147483647));
    return () => window.clearTimeout(timer);
  }, [weekly]);
  useEffect(() => {
    if (!showPrevious) return;
    let active = true;
    apiRequest<Weekly>(`/api/engagement/weekly?period=previous${previousWeek ? `&week=${encodeURIComponent(previousWeek)}` : ''}`).then(data => {
      if (active) setPreviousResult({ data });
    }).catch(() => { if (active) setPreviousResult({ error: 'Не удалось загрузить итоги.' }); });
    return () => { active = false; };
  }, [showPrevious, version, previousWeek]);
  const retry = () => setVersion(v => v + 1);
  async function revoke(token: string) {
    if (busy) return;
    setBusy(token); setError('');
    try { await apiRequest(`/api/engagement/shares/${token}/revoke`, {}, 'POST'); retry(); }
    catch { setError('Не удалось отозвать ссылку. Попробуйте ещё раз.'); }
    finally { setBusy(''); }
  }
  return <main className="community-page community-hub">
    {weekly && communityTrackImage(weekly.track_id) && <div className="community-backdrop" aria-hidden="true"><img src={communityTrackImage(weekly.track_id)} alt="" width="1152" height="768" /></div>}
    <header className="community-header"><h1>Сообщество</h1><p>Побейте время на трассе. Соберите друзей в своей лиге.</p></header>
    <section className="community-spotlight" aria-labelledby="community-weekly-heading">
      <div className="community-challenge-copy">
        <div className="community-section-heading"><HomeIcon name="race" /><h2 id="community-weekly-heading">Трасса недели</h2></div>
        {weeklyResult.error ? <div className="community-error" role="alert"><p>{weeklyResult.error}</p><button onClick={retry}>Повторить</button></div>
          : !weekly ? <p role="status">Загружаем соревнование…</p> : <>
            <h3 className="community-track-name">{weekly.name}</h3>
            <p className="community-challenge-intro">Три круга. Ваше лучшее время.</p>
            <p className="community-period"><strong>{now < new Date(weekly.end).getTime() ? 'Идёт соревнование' : 'Соревнование завершено'}</strong><span>До <time dateTime={weekly.end}>{new Date(weekly.end).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}</time></span></p>
            <Link className="community-primary" to={`/race-game?track=${encodeURIComponent(weekly.track_id)}&weekly=1`}><HomeIcon name="arcade" />Проехать три круга</Link>
            {auth.signedIn && paceResult.data && paceResult.data.track_id === weekly.track_id && paceResult.data.week === weekly.start.slice(0, 10) ? <div className="community-pace"><HomeIcon name="quali" /><p>Ваше место <strong>#{paceResult.data.place}</strong> · <strong>{time(paceResult.data.time_ms)}</strong>{paceResult.data.rival && <small>До времени лидера — {(Math.max(0, paceResult.data.time_ms - paceResult.data.rival.time_ms) / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 3 })} с</small>}</p></div>
              : weekly.entries.length > 0 && <p className="community-target">Время лидера <strong>{time(weekly.entries[0].time_ms)}</strong><span>{weekly.entries[0].name}</span></p>}
            {auth.signedIn && paceResult.error && <div className="community-error" role="alert"><p>{paceResult.error}</p><button onClick={retry}>Повторить</button></div>}
            <details className="community-rules"><summary>Как попасть в зачёт</summary><p>Завершите три круга и сохраните результат, включив участие в рейтинге. В зачёт идут заезды этой недели. Постоянные рекорды не обнуляются.</p></details>
          </>}
      </div>
      {weekly && <CommunityTrackPreview key={weekly.track_id} trackId={weekly.track_id} />}
    </section>
    <div className="community-grid">
      <section className="community-panel" aria-labelledby="community-results-heading">
        <div className="community-section-heading"><HomeIcon name="quali" /><h2 id="community-results-heading">Заезды недели</h2></div>
        {weekly && (weekly.entries.length ? <>
          <div className="community-ranking-labels" aria-hidden="true"><span>Участник</span><span>Лучшее время</span></div>
          <div id="community-current-results"><Ranking entries={weekly.entries} limit={showAll ? 50 : 5} /></div>
          {weekly.entries.length > 5 && <button className="community-disclosure" aria-expanded={showAll} aria-controls="community-current-results" onClick={() => setShowAll(value => !value)}><span>{showAll ? 'Свернуть таблицу' : `Показать ещё (${weekly.entries.length - 5})`}</span><HomeIcon name={showAll ? 'chevronDown' : 'chevronRight'} /></button>}
        </> : <div className="community-first-finish"><HomeIcon name="race" /><h3>Первый финиш может быть вашим</h3><p>Пока нет заездов — можно открыть таблицу первым.</p></div>)}
        {!weekly && <p>{weeklyResult.error ? 'Таблица появится после загрузки соревнования.' : 'Загружаем результаты…'}</p>}
        <div className="community-archive">
          <button className="community-disclosure" aria-expanded={showPrevious} aria-controls="previous-week-results" onClick={() => setShowPrevious(value => !value)}><span>{showPrevious ? 'Скрыть итоги прошлой недели' : 'Итоги прошлой недели'}</span><HomeIcon name={showPrevious ? 'chevronDown' : 'chevronRight'} /></button>
          {showPrevious && <div id="previous-week-results" className="community-previous">
            <h3>Итоги недели · Закончилась</h3>
            {previousResult.error ? <div className="community-error" role="alert"><p>{previousResult.error}</p><button onClick={retry}>Повторить</button></div> : !previous ? <p role="status">Загружаем итоги…</p> : <>
              <p>{previous.name} · {new Date(previous.start).toLocaleDateString('ru-RU')} — {new Date(previous.end).toLocaleDateString('ru-RU')}</p>
              <Ranking entries={previous.entries} winners />
            </>}
          </div>}
        </div>
      </section>
      <section className="community-panel community-leagues" aria-labelledby="community-leagues-heading">
        <div className="community-crew" aria-hidden="true">{(['cobalt', 'scarlet', 'mint'] as const).map(color => <span key={color}><AvatarPortrait avatar={{ helmet: color, suit: color, background: color }} /></span>)}</div>
        <h2 id="community-leagues-heading">Лига вашей компании</h2>
        <p>Соревнуйтесь в прогнозах с друзьями. Весь сезон или мини-чемпионат по выбранным этапам — решаете вы.</p>
        <CommunityLink to={auth.signedIn ? '/predictions?tab=leagues' : '/account?returnTo=leagues'} icon="social">Создать лигу или мини-чемпионат</CommunityLink>
        {auth.signedIn && <div className="community-my-leagues">
          {leaguesResult.error ? <div className="community-error" role="alert"><p>{leaguesResult.error}</p><button onClick={retry}>Повторить</button></div> : !leaguesResult.data ? <p role="status">Загружаем ваши лиги…</p> : leaguesResult.data.length > 0 && <>
            <h3>Ваши лиги</h3>{leaguesResult.data.slice(0, 3).map(league => <Link key={league.id} className="community-league-link" to={`/predictions?tab=leagues&league=${league.id}${league.season ? `&season=${league.season}` : ''}`}><span><strong>{league.name}</strong><small>{league.mode === 'cup' ? 'Мини-чемпионат' : 'Сезон'}</small></span><HomeIcon name="chevronRight" /></Link>)}
          </>}
        </div>}
        <div className="community-destinations">
          <CommunityLink to="/predictions" icon="predictions"><strong>Мой прогноз</strong><small>Выберите подиум — после гонки получите очки и личный разбор.</small></CommunityLink>
          {auth.signedIn && <>
            <CommunityLink to="/predictions?tab=history" icon="history">Мой сезон и разбор этапа</CommunityLink>
            <CommunityLink to="/settings" icon="notifications">Выбрать напоминания</CommunityLink>
          </>}
        </div>
      </section>
    {auth.signedIn && <section className="community-panel community-personal" aria-labelledby="community-personal-heading">
      <div className="community-section-heading"><HomeIcon name="social" /><h2 id="community-personal-heading">Друзья и достижения</h2></div>
      {mineResult.error ? <div className="community-error" role="alert"><p>{mineResult.error}</p><button onClick={retry}>Повторить</button></div> : !mine ? <p role="status">Загружаем достижения…</p> : <>
        {!mine.badges.length && <p>Соберите свою компанию — начните с первого приглашения.</p>}
        <ul className="community-achievements">{[
          { badge: 'Собрал первую лигу', title: 'Собрать свою лигу', text: 'В вашей лиге участвует хотя бы один друг.', icon: 'social' as const },
          { badge: 'Друг принял вызов', title: 'Бросить вызов другу', text: 'Друг сохранит заезд по вашей карточке-вызову.', icon: 'race' as const },
          { badge: 'Привёл трёх участников', title: 'Собрать троих', text: 'Трое приглашённых сохранят прогноз или заезд.', icon: 'predictions' as const },
          ...mine.badges.filter(badge => !['Собрал первую лигу', 'Друг принял вызов', 'Привёл трёх участников'].includes(badge)).map(badge => ({ badge, title: badge, text: 'Достижение получено.', icon: 'favorite' as const })),
        ].map(goal => {
          const earned = mine.badges.includes(goal.badge);
          return <li key={goal.badge} className={earned ? 'is-earned' : undefined}><span className="community-achievement-symbol"><HomeIcon name={goal.icon} /></span><span><strong>{earned ? goal.badge : goal.title}</strong><small>{goal.text}</small></span>{earned && <span className="community-achievement-check" aria-label="Достижение получено"><HomeIcon name="check" /></span>}</li>;
        })}</ul>
        {(mine.referrals.arrived > 0 || mine.referrals.activated > 0 || mine.referrals.returned > 0) && <details className="community-invitations"><summary>По вашим приглашениям</summary><dl className="community-referrals"><div><dt>Присоединились</dt><dd>{mine.referrals.arrived}</dd></div><div><dt>Сохранили прогноз или заезд</dt><dd>{mine.referrals.activated}</dd></div><div><dt>Вернулись на другой этап</dt><dd>{mine.referrals.returned}</dd></div></dl></details>}
        {mine.shares.length ? <details className="community-shares"><summary>Ваши публичные карточки ({mine.shares.length})</summary>
          {error && <p role="alert">{error}</p>}
          {mine.shares.map(share => <div className="community-share-row" key={share.token}><span>{share.title}</span>{share.active ? <><Link to={`/share/${share.token}`}>Открыть</Link><button disabled={Boolean(busy)} onClick={() => void revoke(share.token)}>{busy === share.token ? 'Отзываем…' : 'Отозвать ссылку'}</button></> : <small>Истекла или недоступна</small>}</div>)}
          <small>Отзыв закрывает ссылку, но не удаляет отправленные сообщения и скачанные изображения.</small>
        </details> : <div className="community-sharing-hint"><HomeIcon name="contact" /><p>Поделитесь заездом или приглашением в лигу — здесь можно будет управлять ссылками.</p></div>}
        <details className="community-achievement-help"><summary>Что учитывается</summary><p>Только реальные сохранения, не открытия ссылки. Достижения не добавляют очков в прогнозах.</p></details>
      </>}
    </section>}
    </div>
    {auth.loaded && !auth.signedIn && <p className="community-signin"><HomeIcon name="account" /><span><Link to="/account?returnTo=community">Войдите</Link>, чтобы сохранять результаты и видеть достижения.</span></p>}
  </main>;
}
