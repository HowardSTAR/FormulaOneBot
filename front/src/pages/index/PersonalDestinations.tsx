import { Link } from 'react-router-dom';
import { HomeIcon } from './HomeIcon';
import './home-sections.css';

const track = `${import.meta.env.BASE_URL}race-game/assets/emerald-loop-track.png`;
type Destination = 'predictions' | 'reminders' | 'results' | 'community';

/* Destination previews are decorative, never a substitute for personal data. */
function DestinationPreview({ kind }: { kind: Destination }) {
  if (kind === 'community') return <div className="home-media-preview home-game-preview--track" aria-hidden="true"><img src={track} alt="" width="512" height="512" loading="lazy" /></div>;
  return <div className={`home-media-preview personal-destination-preview personal-destination-preview--${kind}`} aria-hidden="true">
    {kind === 'predictions' ? <><span><HomeIcon name="predictions" /></span><span><HomeIcon name="race" /></span></>
      : kind === 'reminders' ? <>{['Пт', 'Сб', 'Вс'].map(day => <span key={day}>{day}<HomeIcon name="notifications" /></span>)}</>
      : <>{[2, 1, 3].map(place => <span key={place}>{place}</span>)}</>}
  </div>;
}

export function PersonalDestinations() {
  const links: { kind: Destination; to: string; label: string }[] = [
    { kind: 'predictions', to: '/predictions', label: 'Мой прогноз' },
    { kind: 'reminders', to: '/settings', label: 'Напоминания' },
    { kind: 'results', to: '/predictions?tab=history', label: 'Результаты прогнозов' },
    { kind: 'community', to: '/community', label: 'С друзьями · трасса недели' },
  ];
  return <nav className="personal-destinations" aria-label="Личные разделы"><ul>{links.map(({ kind, to, label }) => <li key={kind} className={`personal-destination--${kind}`}>
    <Link to={to} className="home-media-tile personal-destination"><DestinationPreview kind={kind} /><span className="home-media-caption"><strong>{label}</strong></span><span className="home-media-enter"><HomeIcon name="chevronRight" /></span></Link>
  </li>)}</ul></nav>;
}
