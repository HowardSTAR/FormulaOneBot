import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { useHeroData } from '../context/useHeroData';
import { useMediaQuery } from '../helpers/useMediaQuery';
import { GlassSwitch } from '../pages/index/GlassSwitch';
import { HomeIcon } from '../pages/index/HomeIcon';
import { useVisitReminder } from './useVisitReminder';
import { useDockRating } from './useDockRating';
import { AnimatedTrackMap } from './AnimatedTrackMap';
import './home-dock.css';

const destinations = [
  { id: 'home', label: 'Главная', to: '/', icon: 'home' },
  { id: 'calendar', label: 'Календарь', to: '/season', icon: 'calendar' },
  { id: 'predictions', label: 'Прогнозы', to: '/predictions', icon: 'predictions' },
  { id: 'community', label: 'Сообщество', to: '/community', icon: 'social' },
  { id: 'menu', label: 'Меню', to: '/menu', icon: 'menu' },
] as const;

export function HomeDock() {
  const { pathname, search } = useLocation();
  const mobile = useMediaQuery('(max-width: 899px)');
  const allowed = !/^\/(admin|race-game|reaction-game|reflex-grid-game|account|reset-password)(\/|$)/.test(pathname);
  const auth = useAuthState();
  const { nextRace } = useHeroData();
  const { reminder, close } = useVisitReminder({ enabled: mobile && allowed, includeHome: true });
  const rating = useDockRating(mobile && allowed && pathname !== '/voting', auth, nextRace?.season || new Date().getFullYear());
  const [panel, setPanel] = useState<'update' | 'rating'>('rating');
  const [hidden, setHidden] = useState(false);
  const dock = useRef<HTMLDivElement>(null);
  useEffect(() => { const reset = () => { setPanel('rating'); setHidden(false); }; window.addEventListener(AUTH_CHANGED_EVENT, reset); return () => window.removeEventListener(AUTH_CHANGED_EVENT, reset); }, []);
  const ratingPrompt = Boolean(rating.data && (!rating.data.value || rating.celebrate));
  const showRating = ratingPrompt && (panel === 'rating' || !reminder);
  const hasAccessory = !hidden && Boolean(reminder || ratingPrompt);
  const selected = pathname === '/' ? 'home' : /^\/(season|race-details|next-race|.*-results)$/.test(pathname) ? 'calendar' : pathname.startsWith('/predictions') ? 'predictions' : pathname === '/community' ? 'community' : 'menu';
  useEffect(() => {
    const node = dock.current;
    if (!node || !mobile || !allowed) return;
    const measure = () => document.documentElement.style.setProperty('--home-dock-space', `${node.getBoundingClientRect().height + 24}px`);
    measure(); const observer = new ResizeObserver(measure); observer.observe(node);
    return () => { observer.disconnect(); document.documentElement.style.removeProperty('--home-dock-space'); };
  }, [mobile, allowed]);
  if (!allowed) return null;
  const votePath = rating.data ? `/voting?season=${rating.data.season}&round=${rating.data.race.round}` : '/voting';
  return <div className="home-dock" ref={dock}>
    {hasAccessory && <aside className={`home-dock-card ${showRating ? 'home-dock-card--rating' : 'home-dock-card--update'}`} aria-label={showRating ? 'Оценить последний этап' : 'Актуальное напоминание'}>
      {showRating && rating.data ? <>
        <span className="home-dock-feedback" id="dock-rating-label">{rating.data.race.event_name}. {rating.data.value ? `Ваша оценка: ${rating.data.value} из 5` : 'Как вам последний этап?'}</span>
        <div className="home-dock-rating-row">
          <button type="button" className="home-dock-track" onClick={() => reminder ? setPanel('update') : setHidden(true)} aria-label={reminder ? 'Показать актуальное напоминание' : 'Скрыть оценку гонки'} title={rating.data.race.event_name}>
            <AnimatedTrackMap fitRoute animate={false} eventName={rating.data.race.event_name} season={rating.data.season} className="home-dock-track-map" svgClassName="home-dock-track-svg" loadingClassName="home-dock-track-loading" />
          </button>
          <div className="home-dock-stars" role="group" aria-label="Оценка последнего этапа" aria-describedby="dock-rating-label" aria-busy={rating.busy} data-celebrate={rating.celebrate || undefined}>
            {[1, 2, 3, 4, 5].map(value => auth.signedIn ? <button key={value} type="button" className={value <= rating.data!.value ? 'is-filled' : undefined} aria-label={`Оценить гонку на ${value} из 5`} aria-pressed={value === rating.data!.value} disabled={rating.busy || !rating.data!.canRate} onClick={() => void rating.rate(value)} data-analytics-action="vote_submit"><HomeIcon name="favorite" /></button>
              : <Link key={value} to="/account" aria-label={`Войти и оценить гонку на ${value} из 5`}><HomeIcon name="favorite" /></Link>)}
            {rating.celebrate && <span className="home-dock-sparkles" aria-hidden="true">{[0, 1, 2].map(i => <i key={i}><HomeIcon name="favorite" /></i>)}</span>}
          </div>
          <Link className="home-dock-rating-open" to={votePath} aria-label={`Открыть оценки: ${rating.data.race.event_name}`}><HomeIcon name="chevronRight" /></Link>
        </div>
        <span className="home-dock-feedback" role="status" aria-live="polite">{rating.busy ? 'Сохраняем оценку…' : rating.celebrate ? 'Оценка сохранена' : ''}</span>
        {rating.error && <p className="home-dock-error" role="alert">{rating.error} {rating.data.canRate ? 'Выберите звезду, чтобы повторить.' : <button type="button" onClick={rating.retry}>Обновить оценку</button>}</p>}
      </> : reminder && <div className="home-dock-card-heading">
        <Link className="home-dock-copy" to={reminder.to} onClick={close}><strong>{reminder.title}</strong><small>{reminder.detail}</small></Link>
        {ratingPrompt && <button type="button" className="home-dock-next" onClick={() => setPanel('rating')} aria-label="Оценить последний этап"><HomeIcon name="favorite" /></button>}
        <button type="button" className="home-dock-close" onClick={() => { setHidden(true); close(); }} aria-label="Скрыть подсказку"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
      </div>}
    </aside>}
    <GlassSwitch className="home-dock-nav" label="Основная навигация" selected={selected} items={destinations.map(item => item.id === 'menu' ? { ...item, state: { menuFrom: pathname + search } } : item)} />
  </div>;
}
