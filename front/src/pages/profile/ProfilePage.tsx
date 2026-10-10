import { useEffect, useState, type CSSProperties } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest, ApiError } from '../../helpers/api';
import { BackButton } from '../../components/BackButton';
import { ShareButton } from '../../components/ShareButton';
import AvatarEditor, { type ProfileStyle as Style } from './AvatarEditor';
import { avatarUrl, defaultAvatar, type Avatar, type AvatarOptions } from './avatar';
import { ProfileFavorites, type ProfileFavoritesData } from './ProfileFavorites';
import './profile.css';

type Person = { user_id: number; display_name: string; tier: number; tier_name: string; supporter: boolean; style: Style; avatar?: Avatar; avatar_options?: AvatarOptions; favorites?: ProfileFavoritesData };
type Prediction = { round: number; event_name: string | null; points: number | null; max_points: number | null; winner_driver: string; second_driver: string; third_driver: string; pole_driver: string; fastest_lap_driver: string; fourth_driver: string; fifth_driver: string; first_retirement_driver: string; safety_car: number; sprint_pole_driver: string | null; sprint_winner_driver: string | null };
type Profile = Person & { is_owner: boolean; season: number; seasons: number[]; best_prediction: Prediction | null; predictions: Prediction[]; records: { track_id: string; track_name: string; best_time_ms: number; attempts: number }[]; total_points: number; scored_rounds: number; options: Record<keyof Style, Record<string, number>> };
const colors: Record<string, string> = { white: '#f4f4f5', red: '#ff786e', blue: '#8ebcff', gold: '#f5ce73', mint: '#8ce5c7' };
const fields: [keyof Prediction, string][] = [['sprint_pole_driver', 'Спринт-поул'], ['sprint_winner_driver', 'Спринт-победа'], ['pole_driver', 'Поул'], ['winner_driver', 'Победитель'], ['second_driver', '2 место'], ['third_driver', '3 место'], ['fourth_driver', '4 место'], ['fifth_driver', '5 место'], ['fastest_lap_driver', 'Лучший круг'], ['first_retirement_driver', 'Первый сход'], ['safety_car', 'Машина безопасности']];
function Answers({ prediction }: { prediction: Prediction }) {
  return <dl className="profile-answers">{fields.filter(([key]) => prediction[key] !== null).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{key === 'safety_car' ? prediction[key] ? 'Да' : 'Нет' : prediction[key]}</dd></div>)}</dl>;
}
function lapTime(ms: number) { return `${Math.floor(ms / 60000)}:${((ms % 60000) / 1000).toFixed(3).padStart(6, '0')}`; }

export default function ProfilePage({ embedded = false }: { embedded?: boolean }) {
  const { userId } = useParams();
  const [params, setParams] = useSearchParams();
  const requestedSeason = Number(params.get('season'));
  const season = Number.isInteger(requestedSeason) && requestedSeason >= 1950 && requestedSeason <= 2100 ? requestedSeason : undefined;
  const setSeason = (year: number) => setParams(previous => { const next = new URLSearchParams(previous); next.set('season', String(year)); return next; });
  const [profile, setProfile] = useState<Profile | null>(null);
  const [league, setLeague] = useState<(Person & { place: number; total_points: number })[] | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [avatarOpen, setAvatarOpen] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setLeague(null); setNotice(''); setAvatarOpen(false);
    apiRequest<Profile>(`/api/profiles/${userId || 'me'}`, { season }).then(data => {
      if (active) setProfile(data);
    }).catch(e => { if (active) setError(e instanceof ApiError && e.status === 401 ? 'Войдите в аккаунт, чтобы увидеть свой профиль, рекорды и прогнозы.' : e instanceof Error ? e.message : 'Не удалось загрузить профиль'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId, season]);
  async function showLeague() {
    setBusy(true); setNotice('');
    try { const value = await apiRequest<{ entries: (Person & { place: number; total_points: number })[] }>('/api/profiles/supporters', { season: profile?.season }); setLeague(value.entries); }
    catch (e) { setNotice(e instanceof Error ? e.message : 'Не удалось загрузить зачёт'); }
    finally { setBusy(false); }
  }
  const style = profile?.style;
  return <main className="user-profile-page">
    {!embedded && <div className="profile-top"><BackButton fallback="/profile" /><span>ПРОФИЛЬ УЧАСТНИКА</span><Link to="/profile">Мой профиль</Link></div>}
    {loading ? <p role="status">Загружаем профиль…</p> : error ? <div role="alert"><p>{error}</p><Link to="/account">Войти в аккаунт</Link></div> : profile && style && <>
      {profile.is_owner && <div className="profile-sharing"><ShareButton options={{kind:'profile',season:profile.season}}>Поделиться профилем</ShareButton></div>}
      <section className={`profile-hero profile-bg-${style.background}`} style={{ '--profile-nick': colors[style.color] } as CSSProperties}>
        {profile.is_owner ? <div className="profile-avatar-control"><button type="button" className={`profile-avatar profile-avatar-button profile-frame-${style.frame}`} aria-label="Изменить аватар и оформление" title="Настроить гонщика и оформление профиля" onClick={() => { setNotice(''); setAvatarOpen(true); }}><img src={avatarUrl(profile.avatar || defaultAvatar)} alt="" width="88" height="88" /></button><button type="button" className="profile-avatar-edit" onClick={() => { setNotice(''); setAvatarOpen(true); }}>Аватар и оформление</button></div> : <div className={`profile-avatar profile-frame-${style.frame}`}><img src={avatarUrl(profile.avatar || defaultAvatar)} alt="Аватар гонщика" width="88" height="88" /></div>}
        <div className="profile-identity"><p className="profile-eyebrow">TURBOTEARS / УЧАСТНИК</p><h1>{profile.display_name} {profile.supporter && <span className="profile-supporter" title={profile.tier_name} aria-label={`Сторонник · ${profile.tier_name}`}>◆</span>}</h1><p>{profile.tier_name}</p></div>
        <div className="profile-highlight"><span>ЛУЧШИЙ ПРОГНОЗ · {profile.season}</span>{profile.best_prediction ? <><strong>{profile.best_prediction.points}<small> / {profile.best_prediction.max_points ?? '—'} баллов</small></strong><p>{profile.best_prediction.event_name || `Этап ${profile.best_prediction.round}`}</p></> : <p>Первый результат ещё впереди</p>}</div>
      </section>
      <div className="profile-season"><h2>Сезон в цифрах</h2><label>Сезон <select aria-label="Сезон профиля" value={profile.season} onChange={e => setSeason(Number(e.target.value))}>{profile.seasons.map(year => <option key={year}>{year}</option>)}</select></label></div>
      <div className="profile-stats"><div><strong>{profile.total_points}</strong><span>Баллов за сезон</span></div><div><strong>{profile.scored_rounds}</strong><span>Рассчитанных прогнозов</span></div><div><strong>{profile.records.length}</strong><span>Трасс с рекордами</span></div></div>
      <div className="profile-columns"><section className="profile-panel"><h2>Рекорды на трассах</h2>{profile.records.length ? profile.records.map(record => <div className="profile-record" key={record.track_id}><div><strong>{record.track_name}</strong><p>Заездов: {record.attempts}</p></div><b>{lapTime(record.best_time_ms)}</b></div>) : <p className="profile-muted">Пока нет опубликованных рекордов на трассах.</p>}{profile.is_owner && <Link to="/race-game">На трассу →</Link>}</section>
      <section className="profile-panel"><h2>Прогнозы · {profile.season}</h2>{!profile.is_owner && <p className="profile-muted">Ответы показываются после начисления баллов.</p>}{profile.predictions.length ? profile.predictions.map(prediction => <details className="profile-prediction" key={prediction.round}><summary><span>{prediction.event_name || `Этап ${prediction.round}`}{profile.best_prediction?.round === prediction.round && <small>Лучший за сезон</small>}</span><b>{prediction.points === null ? 'Ожидает расчёта' : `${prediction.points} / ${prediction.max_points ?? '—'}`}</b></summary><Answers prediction={prediction} /></details>) : <p className="profile-muted">Прогнозов за этот сезон пока нет.</p>}{profile.is_owner && <Link to="/predictions">Сделать прогноз →</Link>}</section></div>
      {profile.is_owner && <section className="profile-panel"><h2>Клуб TurboTears</h2><p className="profile-muted">Общий зачёт прогнозов за сезон для уровней «На старт», «Свой стиль» и «Полный газ».</p>{profile.supporter ? <><button className="profile-primary" disabled={busy} onClick={() => void showLeague()}>Показать зачёт · {profile.season}</button>{league && (league.length ? <ol className="profile-league">{league.map(entry => <li key={entry.user_id}><Link to={`/profile/${entry.user_id}`}>{entry.display_name} ◆</Link><b>{entry.total_points} баллов</b></li>)}</ol> : <p>В клубе пока нет участников с профилем прогнозов.</p>)}</> : <a href="https://boosty.to/turbotears" target="_blank" rel="noopener noreferrer">Присоединиться на Boosty →</a>}</section>}
      <ProfileFavorites favorites={profile.favorites || { drivers: [], teams: [] }} owner={profile.is_owner} />
      {notice && <p role="status" className="profile-notice">{notice}</p>}
      {profile.is_owner && avatarOpen && profile.avatar_options && <AvatarEditor value={profile.avatar || defaultAvatar} options={profile.avatar_options} style={profile.style} styleOptions={profile.options} tier={profile.tier} onClose={() => setAvatarOpen(false)} onAvatarSave={avatar => { setProfile(p => p ? { ...p, avatar } : p); setNotice('Аватар сохранён'); }} onStyleSave={style => { setProfile(p => p ? { ...p, style } : p); setNotice('Оформление сохранено'); }} />}
    </>}
  </main>;
}
