import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest, ApiError } from '../../helpers/api';
import { BackButton } from '../../components/BackButton';
import { ShareButton } from '../../components/ShareButton';
import SupporterBadge from '../../components/SupporterBadge';
import AvatarEditor, { type ProfileStyle as Style } from './AvatarEditor';
import { avatarUrl, defaultAvatar, type Avatar, type AvatarOptions } from './avatar';
import { warmAvatarSprites } from './avatarSprites';
import { ProfileFavorites, type ProfileFavoritesData } from './ProfileFavorites';
import './profile.css';
import ProfileTrophies from './ProfileTrophies';
import SupporterLeague from './SupporterLeague';
import { trophyImage, type TrophyAward } from '../../helpers/trophies';
import ProfileGuide from './ProfileGuide';
import { PROFILE_GUIDE_START } from '../../helpers/profileGuide';
import { AUTH_CHANGED_EVENT } from '../../helpers/auth';
import EmailVerification from './EmailVerification';
import { CustomSelect } from '../../components/CustomSelect';
import '../index/home-controls.css';
import './profile-controls.css';
import './profile-backgrounds.css';

type Person = { user_id: number; display_name: string; tier: number; tier_name: string; supporter: boolean; style: Style; avatar?: Avatar; avatar_options?: AvatarOptions; favorites?: ProfileFavoritesData };
type Prediction = { round: number; event_name: string | null; points: number | null; max_points: number | null; winner_driver: string; second_driver: string; third_driver: string; pole_driver: string; fastest_lap_driver: string; fourth_driver: string; fifth_driver: string; first_retirement_driver: string; safety_car: number; sprint_pole_driver: string | null; sprint_winner_driver: string | null };
type Profile = Person & { is_owner: boolean; email?: string | null; email_verified?: boolean; profile_guide_seen?: boolean; season: number; seasons: number[]; best_prediction: Prediction | null; predictions: Prediction[]; records: { track_id: string; track_name: string; best_time_ms: number; attempts: number }[]; total_points: number; scored_rounds: number; options: Record<keyof Style, Record<string, number>> };
const fields: [keyof Prediction, string][] = [['sprint_pole_driver', 'Спринт-поул'], ['sprint_winner_driver', 'Спринт-победа'], ['pole_driver', 'Поул'], ['winner_driver', 'Победитель'], ['second_driver', '2 место'], ['third_driver', '3 место'], ['fourth_driver', '4 место'], ['fifth_driver', '5 место'], ['fastest_lap_driver', 'Лучший круг'], ['first_retirement_driver', 'Первый сход'], ['safety_car', 'Машина безопасности']];
function Answers({ prediction }: { prediction: Prediction }) {
  const finish = ['winner_driver', 'second_driver', 'third_driver', 'fourth_driver', 'fifth_driver'] as const;
  return <div className="profile-answers">
    <ol className="profile-answer-finish" aria-label="Прогноз финишной пятёрки">{finish.map((key, index) => <li key={key} aria-label={`${index + 1} место: ${prediction[key]}`}><span aria-hidden="true">{index + 1}</span><strong>{prediction[key]}</strong></li>)}</ol>
    <dl className="profile-answer-events">{fields.filter(([key]) => !finish.includes(key as typeof finish[number]) && prediction[key] !== null).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{key === 'safety_car' ? prediction[key] ? 'Да' : 'Нет' : prediction[key]}</dd></div>)}</dl>
  </div>;
}
function lapTime(ms: number) { return `${Math.floor(ms / 60000)}:${((ms % 60000) / 1000).toFixed(3).padStart(6, '0')}`; }

export default function ProfilePage({ embedded = false }: { embedded?: boolean }) {
  const location = useLocation();
  const welcome = location.state as { registered?: boolean; emailSent?: boolean } | null;
  const { userId } = useParams();
  const [params, setParams] = useSearchParams();
  const requestedSeason = Number(params.get('season'));
  const season = Number.isInteger(requestedSeason) && requestedSeason >= 1950 && requestedSeason <= 2100 ? requestedSeason : undefined;
  const setSeason = (year: number) => setParams(previous => { const next = new URLSearchParams(previous); next.set('season', String(year)); return next; });
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState('');
  const [authRequired, setAuthRequired] = useState(false);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [authVersion, setAuthVersion] = useState(0);
  const [requestContext, setRequestContext] = useState({ userId, season, authVersion });
  const [trophyBadge, setTrophyBadge] = useState<TrophyAward | null>(null);
  const updateTrophyBadge = useCallback((value: TrophyAward | null) => setTrophyBadge(value), []);
  if (requestContext.userId !== userId || requestContext.season !== season || requestContext.authVersion !== authVersion) {
    // Reset before rendering children so a new request never displays stale controls.
    setRequestContext({ userId, season, authVersion });
    setLoading(true);
    setError('');
    setAuthRequired(false);
    setNotice('');
    setAvatarOpen(false);
    setTrophyBadge(null);
    // Keep the current guide mounted across seasons, but never across accounts or profiles.
    if (requestContext.userId !== userId || requestContext.authVersion !== authVersion) setProfile(null);
  }
  useEffect(() => {
    const refresh = () => setAuthVersion(value => value + 1);
    window.addEventListener(AUTH_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, refresh);
  }, []);
  useEffect(() => {
    let active = true;
    apiRequest<Profile>(`/api/profiles/${userId || 'me'}`, { season }).then(data => {
      if (active) setProfile(data);
    }).catch(e => { if (active) {
      const unauthorized = e instanceof ApiError && e.status === 401;
      setAuthRequired(unauthorized);
      setError(unauthorized ? 'Войдите в аккаунт, чтобы увидеть свой профиль, рекорды и прогнозы.' : e instanceof Error ? e.message : 'Не удалось загрузить профиль');
    } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId, season, authVersion]);
  useEffect(() => {
    if (profile?.is_owner && profile.avatar_options) return warmAvatarSprites();
  }, [profile?.is_owner, profile?.avatar_options]);
  const style = profile?.style;
  async function refreshSubscription() {
    const updated = await apiRequest<Profile>(`/api/profiles/${userId || 'me'}`, { season });
    setProfile(current => current?.user_id === updated.user_id ? {
      ...current, tier: updated.tier, tier_name: updated.tier_name, supporter: updated.supporter, style: updated.style,
    } : current);
    return { tier: updated.tier, style: updated.style };
  }
  return <main className="user-profile-page">
    {!embedded && <div className="profile-top"><BackButton fallback="/profile" /><Link to="/profile">Мой профиль</Link></div>}
    {loading ? <div className="profile-state" role="status"><h1>Профиль</h1><p>Загружаем профиль…</p></div> : error ? <div className="profile-state"><h1>{authRequired ? 'Твой профиль TurboTears' : 'Профиль недоступен'}</h1><p role="alert">{error}</p>{authRequired ? <Link className="profile-panel-action" to="/account">Войти в аккаунт</Link> : <button type="button" className="profile-panel-action" onClick={() => setAuthVersion(value => value + 1)}>Повторить загрузку</button>}</div> : profile && style && <>
      {profile.is_owner && profile.email && !profile.email_verified && <EmailVerification key={profile.user_id} email={profile.email} emailSent={welcome?.emailSent} registered={welcome?.registered} />}
      <div className="profile-content">
      <section className={`profile-hero${profile.is_owner ? ' profile-hero--owner' : ''} profile-bg-${style.background} profile-color-${style.color}`} aria-label="Профиль участника">
        {profile.is_owner ? <div className="profile-avatar-control"><button type="button" className={`profile-avatar profile-avatar-button profile-frame-${style.frame}`} aria-label="Изменить аватар и оформление" title="Настроить гонщика и оформление профиля" onClick={() => { setNotice(''); setAvatarOpen(true); }}><img src={avatarUrl(profile.avatar || defaultAvatar)} alt="" width="88" height="88" /></button></div> : <div className={`profile-avatar profile-frame-${style.frame}`}><img src={avatarUrl(profile.avatar || defaultAvatar)} alt="Аватар гонщика" width="88" height="88" /></div>}
        <div className="profile-identity"><h1>{profile.display_name} {profile.supporter && <SupporterBadge tierName={profile.tier_name} large />}{trophyBadge && <span className="profile-trophy-badge" role="img" aria-label={`${trophyBadge.name}, ${trophyBadge.tier}${trophyBadge.season ? `, сезон ${trophyBadge.season}` : ''}`}><img src={trophyImage(trophyBadge.family,trophyBadge.level)} alt="" width="36" height="36" /></span>}</h1><p>{profile.tier_name}</p>
        </div>
        {profile.is_owner && <div className="profile-sharing" role="group" aria-label="Действия профиля"><button type="button" className="profile-avatar-edit" aria-label="Аватар и оформление" title="Аватар и оформление" onClick={() => { setNotice(''); setAvatarOpen(true); }}>
          <svg viewBox="0 0 32 32" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 5a11 11 0 1 0 0 22h2a3 3 0 0 0 2-5c-1-1-1-3 1-4l2-1a6 6 0 0 0 3-5"/><circle cx="10" cy="12" r="1.3"/><circle cx="9" cy="19" r="1.3"/><circle cx="15" cy="9" r="1.3"/><path d="m19 17 9-12a1.8 1.8 0 0 1 3 2L21 19m-2-2c-5-1-2 6-6 6 4 3 9-1 8-4Z"/></svg>
        </button><button type="button" className="profile-guide-replay" onClick={() => window.dispatchEvent(new CustomEvent(PROFILE_GUIDE_START,{detail:{userId:profile.user_id}}))}>Возможности профиля</button><ShareButton label="Поделиться профилем" options={{kind:'profile',season:profile.season}}><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 15V3m-4 4 4-4 4 4M7 11H5v10h14V11h-2" /></svg></ShareButton></div>}
        <div className="profile-highlight"><span>ЛУЧШИЙ ПРОГНОЗ · {profile.season}</span>{profile.best_prediction ? <><strong>{profile.best_prediction.points}<small> / {profile.best_prediction.max_points ?? '—'} баллов</small></strong><p>{profile.best_prediction.event_name || `Этап ${profile.best_prediction.round}`}</p></> : <p>Первый результат ещё впереди</p>}</div>
      </section>
      <section className="profile-season-block" aria-labelledby="profile-season-title">
      <div className="profile-season"><h2 id="profile-season-title">Сезон в цифрах</h2><div className="profile-season-picker"><span aria-hidden="true">Сезон</span><CustomSelect ariaLabel="Сезон профиля" value={profile.season} options={profile.seasons.map(year => ({ value: year, label: String(year) }))} onChange={year => setSeason(Number(year))} /></div></div>
      <div className="profile-stats"><div><strong>{profile.total_points}</strong><span>Баллов за сезон</span></div><div><strong>{profile.scored_rounds}</strong><span>Прогнозов с баллами</span></div><div><strong>{profile.records.length}</strong><span>Трасс с рекордами</span></div></div>
      <div className="profile-columns"><section className="profile-panel profile-activity profile-activity--predictions" data-profile-guide="predictions"><div className="profile-panel-art profile-panel-art--podium" aria-hidden="true"><span>2</span><span>1</span><span>3</span></div><h2>Прогнозы · {profile.season}</h2>{!profile.is_owner && <p className="profile-muted">Ответы показываются после начисления баллов.</p>}<div className="profile-activity-body">{profile.predictions.length ? profile.predictions.map(prediction => <details className="profile-prediction" key={prediction.round}><summary><span>{prediction.event_name || `Этап ${prediction.round}`}{profile.best_prediction?.round === prediction.round && <small>Лучший за сезон</small>}</span><b>{prediction.points === null ? 'Ожидает расчёта' : `${prediction.points} / ${prediction.max_points ?? '—'}`}</b></summary><Answers prediction={prediction} /></details>) : <p className="profile-muted">Прогнозов за этот сезон пока нет.</p>}</div>{profile.is_owner && <Link className="profile-panel-action" to="/predictions">Сделать прогноз →</Link>}</section>
      <section className="profile-panel profile-activity profile-activity--records" data-profile-guide="records"><div className="profile-panel-art profile-panel-art--track" aria-hidden="true"><img src={`${import.meta.env.BASE_URL}race-game/assets/emerald-loop-track.png`} alt="" width="512" height="512" loading="lazy" /></div><h2>Рекорды на трассах</h2><div className="profile-activity-body">{profile.records.length ? profile.records.map(record => <div className="profile-record" key={record.track_id}><div><strong>{record.track_name}</strong><p>Заездов: {record.attempts}</p></div><b>{lapTime(record.best_time_ms)}</b></div>) : <p className="profile-muted">Пока нет опубликованных рекордов на трассах.</p>}</div>{profile.is_owner && <Link className="profile-panel-action" to="/race-game">На трассу →</Link>}</section></div>
      </section>
      <ProfileTrophies key={profile.user_id} userId={profile.user_id} owner={profile.is_owner} onBadge={updateTrophyBadge} />
      <ProfileFavorites favorites={profile.favorites || { drivers: [], teams: [] }} owner={profile.is_owner} />
      {profile.is_owner && <SupporterLeague season={profile.season} supporter={profile.supporter} />}
      </div>
      {notice && <p role="status" className="profile-notice">{notice}</p>}
      {profile.is_owner && avatarOpen && profile.avatar_options && <AvatarEditor value={profile.avatar || defaultAvatar} options={profile.avatar_options} style={profile.style} styleOptions={profile.options} tier={profile.tier} onSubscriptionCheck={refreshSubscription} onClose={() => setAvatarOpen(false)} onAvatarSave={avatar => { setProfile(p => p ? { ...p, avatar } : p); setNotice('Аватар сохранён'); }} onStyleSave={style => { setProfile(p => p ? { ...p, style } : p); setNotice('Оформление сохранено'); }} />}
    </>}
    {profile?.is_owner && !error && (!userId || Number(userId)===profile.user_id) && <ProfileGuide key={profile.user_id} userId={profile.user_id} seen={Boolean(profile.profile_guide_seen)} needsEmailVerification={Boolean(profile.email && !profile.email_verified)} />}
  </main>;
}
