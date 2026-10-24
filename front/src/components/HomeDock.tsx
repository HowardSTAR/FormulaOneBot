import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { useHeroData } from '../context/useHeroData';
import { useMediaQuery } from '../helpers/useMediaQuery';
import { GlassSwitch } from '../pages/index/GlassSwitch';
import { HomeIcon } from '../pages/index/HomeIcon';
import { useVisitReminder } from './useVisitReminder';
import { useDockRating } from './useDockRating';
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
  const [panel, setPanel] = useState<'update' | 'rating'>('update');
  const [hidden, setHidden] = useState(false);
  const dock = useRef<HTMLDivElement>(null);
  useEffect(() => { const reset = () => { setPanel('update'); setHidden(false); }; window.addEventListener(AUTH_CHANGED_EVENT, reset); return () => window.removeEventListener(AUTH_CHANGED_EVENT, reset); }, []);
  const showRating = Boolean(rating.data && (panel === 'rating' || !reminder));
  const hasAccessory = !hidden && Boolean(reminder || rating.data);
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
    {hasAccessory && <aside className={`home-dock-card${showRating ? '' : ' home-dock-card--update'}`} aria-label={showRating ? 'Оценить последний этап' : 'Актуальное напоминание'}>
      <div className="home-dock-card-heading">
        {showRating && rating.data ? <Link className="home-dock-copy" to={votePath}><strong>{rating.data.value ? `Ваша оценка: ${rating.data.value} из 5` : 'Как вам последний этап?'}</strong><small>{rating.data.race.event_name}</small></Link>
          : reminder && <Link className="home-dock-copy" to={reminder.to} onClick={close}><strong>{reminder.title}</strong><small>{reminder.detail}</small></Link>}
        {reminder && rating.data && <button type="button" className="home-dock-next" onClick={() => setPanel(showRating ? 'update' : 'rating')} aria-label={showRating ? 'Показать актуальное напоминание' : 'Оценить последний этап'}><HomeIcon name={showRating ? 'notifications' : 'favorite'} /></button>}
        <button type="button" className="home-dock-close" onClick={() => { setHidden(true); if (reminder) close(); }} aria-label="Скрыть подсказку"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
      </div>
      {showRating && rating.data && <>
        {rating.data.canRate ? <div className="home-dock-stars" role="group" aria-label="Оценка последнего этапа" aria-busy={rating.busy} data-celebrate={rating.celebrate || undefined}>
          {[1, 2, 3, 4, 5].map(value => <button key={value} type="button" className={value <= rating.data!.value ? 'is-filled' : undefined} aria-label={`Оценить гонку на ${value} из 5`} aria-pressed={value === rating.data!.value} disabled={rating.busy} onClick={() => void rating.rate(value)} data-analytics-action="vote_submit"><HomeIcon name="favorite" /></button>)}
          {rating.celebrate && <span className="home-dock-sparkles" aria-hidden="true">{[0, 1, 2].map(i => <i key={i}><HomeIcon name="favorite" /></i>)}</span>}
        </div> : <Link className="home-dock-account" to={votePath}>{auth.personalized ? 'Открыть голосование' : auth.signedIn ? 'Связать Telegram и оценить' : 'Войти и оценить'}<HomeIcon name="chevronRight" /></Link>}
        <span className="home-dock-feedback" role="status" aria-live="polite">{rating.busy ? 'Сохраняем оценку…' : rating.celebrate ? 'Оценка сохранена' : ''}</span>
        {rating.error && <p className="home-dock-error" role="alert">{rating.error} Выберите звезду, чтобы повторить.</p>}
      </>}
    </aside>}
    <GlassSwitch className="home-dock-nav" label="Основная навигация" selected={selected} items={destinations.map(item => item.id === 'menu' ? { ...item, state: { menuFrom: pathname + search } } : item)} />
  </div>;
}
