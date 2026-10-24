import { Link } from 'react-router-dom';
import { HomeIcon } from './HomeIcon';
import './home-sections.css';

const track = `${import.meta.env.BASE_URL}race-game/assets/emerald-loop-track.png`;
type Destination = 'account' | 'reminders' | 'favorites' | 'results' | 'community';

/* Destination previews are decorative, never a substitute for personal data. */
function DestinationPreview({ kind }: { kind: Destination }) {
  if (kind === 'community') return <div className="home-media-preview home-game-preview--track" aria-hidden="true"><img src={track} alt="" width="512" height="512" loading="lazy" /></div>;
  return <div className={`home-media-preview personal-destination-preview personal-destination-preview--${kind}`} aria-hidden="true">
    {kind === 'account' ? <><span className="home-preview-avatar home-preview-avatar--red"><HomeIcon name="account" /></span><span className="home-preview-avatar home-preview-avatar--silver"><HomeIcon name="account" /></span></>
      : kind === 'reminders' ? <>{['Пт', 'Сб', 'Вс'].map(day => <span key={day}>{day}<HomeIcon name="notifications" /></span>)}</>
      : kind === 'favorites' ? <><HomeIcon name="drivers" /><HomeIcon name="teams" /></>
      : <>{[2, 1, 3].map(place => <span key={place}>{place}</span>)}</>}
  </div>;
}

export function PersonalDestinations({ personalized }: { personalized: boolean }) {
  const links: { kind: Destination; to: string; label: string }[] = [
    { kind: 'account', to: '/account', label: 'Аккаунт' },
    { kind: 'reminders', to: '/settings', label: 'Напоминания' },
    ...(personalized ? [{ kind: 'favorites' as const, to: '/favorites', label: 'Избранное' }] : []),
    { kind: 'results', to: '/predictions?tab=history', label: 'Результаты прогнозов' },
    { kind: 'community', to: '/community', label: 'С друзьями · трасса недели' },
  ];
  return <nav className="personal-destinations" aria-label="Личные разделы"><ul>{links.map(({ kind, to, label }) => <li key={kind} className={`personal-destination--${kind}`}>
    <Link to={to} className="home-media-tile personal-destination"><DestinationPreview kind={kind} /><span className="home-media-caption"><strong>{label}</strong></span><span className="home-media-enter"><HomeIcon name="chevronRight" /></span></Link>
  </li>)}</ul></nav>;
}
