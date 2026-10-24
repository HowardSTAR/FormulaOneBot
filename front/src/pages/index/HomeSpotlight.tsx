import { useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useHeroData } from '../../context/useHeroData';
import { useAuthState } from '../../helpers/auth';
import { apiAssetUrl } from '../../helpers/api';
import { spotlightTeamMedia } from './spotlight-team-media';
import { carImageUrl, teamLogoUrl } from '../../helpers/f1Assets';
import { optionalNumber } from '../../helpers/presentation';
import Hero from './Hero';
import { HomeIcon } from './HomeIcon';
import { spotlightSlots, type SpotlightSlot } from './spotlight-model';
import { useSpotlightData } from './useSpotlightData';
import { useMediaQuery } from '../../helpers/useMediaQuery';
import './home-spotlight.css';

const memberKeys = ['race', 'driver-1', 'driver-2', 'team'];
function MediaImage({ sources, className, fallback }: { sources: string[]; className: string; fallback?: string }) {
  const [index, setIndex] = useState(0);
  if (index >= sources.length) return fallback ? <span className="home-spotlight-monogram">{fallback}</span> : null;
  return <img className={className} src={sources[index]} alt="" width="640" height="400" loading="lazy" decoding="async" onError={() => setIndex(value => value + 1)} />;
}
function SpotlightImage({ src, fallback }: { src: string; fallback: string }) {
  return <div className="home-spotlight-art" aria-hidden="true"><MediaImage key={src} sources={[src]} className="home-pilot-portrait" fallback={fallback} /></div>;
}
function FavoriteSlide({ slot, season, loaded, failed, favoritesPath, onRetry, favoritesFailed }: { slot: SpotlightSlot; season: number; loaded: boolean; failed: boolean; favoritesPath: string; onRetry: () => void; favoritesFailed: boolean }) {
  const { entry, kind, favorite, unavailable } = slot;
  const team = kind === 'team';
  if (!entry) return <section className="home-favorite-card home-favorite-empty" aria-label={team ? 'Команда' : 'Пилот'}>
    <HomeIcon name={team ? 'teams' : 'drivers'} />
    <h2>{!loaded ? 'Загружаем…' : failed ? 'Данные недоступны' : unavailable ? 'Нет данных за этот сезон' : team ? 'Ваша команда' : 'Ваш пилот'}</h2>
    <p>{unavailable ? 'Сохранённый выбор остаётся в избранном.' : 'Выберите, за кем следить в чемпионате.'}</p>
    {failed ? <button type="button" className="home-glass-button" onClick={onRetry}>Обновить данные</button> : <Link className="home-glass-button" to={favoritesPath}>Выбрать {team ? 'команду' : 'пилота'}<HomeIcon name="chevronRight" /></Link>}
  </section>;
  const points = optionalNumber(entry.points), position = optionalNumber(entry.position);
  const details = team ? `/constructor-details?constructorId=${encodeURIComponent(entry.constructorId || entry.name)}&season=${season}`
    : `/driver-details?code=${encodeURIComponent(entry.code || '')}&driverId=${encodeURIComponent(entry.driverId || '')}&season=${season}`;
  const teamName = team ? entry.name : entry.constructorName || '';
  const official = spotlightTeamMedia(entry.constructorId || '', teamName, season);
  const media = { logo: [...official.logo, teamLogoUrl(entry.constructorId || '', teamName, season)], car: [...official.car, carImageUrl(teamName, season)] };
  const src = entry.imageUrl || apiAssetUrl('/api/pilot-portrait', { code: entry.code, name: entry.name, season, strict: true });
  return <section className={`home-favorite-card${team ? ' home-favorite-card--team' : ''}`} aria-label={entry.name}>
    <div className={team ? 'home-team-car' : 'home-favorite-watermark'} aria-hidden="true"><MediaImage key={media.logo[0]} sources={team ? media.car : media.logo} className="home-team-backdrop-image" /></div>
    <div className="home-favorite-copy">
      <div className="home-favorite-kind"><HomeIcon name={favorite ? 'favorite' : team ? 'teams' : 'drivers'} /><span>{favorite ? team ? 'Избранная команда' : 'Избранный пилот' : team ? 'Лидер среди команд' : 'В лидерах сезона'}</span></div>
      <div className="home-favorite-identity"><h2><Link className="home-favorite-name" to={details} aria-label={`${team ? 'О команде' : 'О пилоте'}: ${entry.name}`}>{entry.name}</Link></h2>{team && <span className="home-team-logo" aria-hidden="true"><MediaImage key={media.logo[0]} sources={media.logo} className="home-team-logo-image" fallback={entry.name.slice(0, 3).toUpperCase()} /></span>}</div>
      <p className="home-favorite-team">{team ? 'Кубок конструкторов' : entry.constructorName || `Сезон ${season}`}</p>
      <dl className="home-favorite-stats"><div><dt>Очки</dt><dd>{points?.toLocaleString('ru-RU') ?? '—'}</dd></div><div><dt>Место</dt><dd>{position && position > 0 ? position : '—'}</dd></div></dl>
      {favoritesFailed && <div className="home-favorite-error" role="status">Избранное не загрузилось. Показаны лидеры. <button type="button" className="home-glass-button" onClick={onRetry}>Повторить</button></div>}
    </div>
    {!team && <SpotlightImage key={src} src={src} fallback={entry.number || entry.code || entry.name.slice(0, 3)} />}
  </section>;
}
function PersonalizeSlide() {
  return <section className="home-favorite-card home-personalize" aria-labelledby="home-personalize-title">
    <div className="home-favorite-copy">
      <h2 id="home-personalize-title">Ваша команда.<br />Ваши пилоты.</h2>
      <p>Зарегистрируйтесь, чтобы видеть здесь своих фаворитов и их очки.</p>
      <Link className="home-glass-button home-glass-button--primary" to="/account?mode=register">Создать аккаунт<HomeIcon name="chevronRight" /></Link>
    </div>
    <div className="home-personalize-symbols" aria-hidden="true"><span><HomeIcon name="drivers" /></span><span><HomeIcon name="drivers" /></span><span><HomeIcon name="teams" /></span></div>
  </section>;
}
export function HomeSpotlight({ season }: { season: number }) {
  const hero = useHeroData(), auth = useAuthState();
  const wide = useMediaQuery('(min-width: 1200px)');
  const { data, retry } = useSpotlightData(season, auth);
  const [params, setParams] = useSearchParams();
  const viewport = useRef<HTMLDivElement>(null);
  const keys = auth.signedIn ? memberKeys : memberKeys.slice(0, 2);
  const count = keys.length;
  const requested = params.get('spotlight') || 'race';
  const active = Math.max(0, keys.indexOf(requested));
  const current = useRef(active);
  const previousCount = useRef(count);
  const previousWide = useRef(wide);
  const scrollTarget = useRef<number | null>(active);
  const touch = useRef<{ x: number; y: number; index: number } | null>(null);
  const slots = spotlightSlots(data?.drivers || [], data?.teams || [], data?.favorites || { drivers: [], teams: [] });
  const guest = !auth.signedIn;
  const visibleSlots = guest ? slots.slice(0, 1) : slots;
  const labels = ['Ближайшая гонка', ...visibleSlots.map((slot, i) => guest ? 'Персонализировать главную' : slot.entry?.name || (i === 2 ? 'Команда' : `Пилот ${i + 1}`))];
  useEffect(() => {
    if (auth.loaded && !auth.signedIn && requested !== 'race' && requested !== 'driver-1') {
      setParams(previous => { const next = new URLSearchParams(previous); next.set('spotlight', 'driver-1'); return next; }, { replace: true, preventScrollReset: true });
    }
  }, [auth.loaded, auth.signedIn, requested, setParams]);
  const select = (index: number) => {
    index = (index + keys.length) % keys.length;
    const node = viewport.current;
    if (!node) return;
    current.current = index;
    scrollTarget.current = index;
    node.scrollTo({ left: node.clientWidth * index, behavior: 'instant' });
    setParams(previous => { const next = new URLSearchParams(previous); if (index) next.set('spotlight', keys[index]); else next.delete('spotlight'); return next; }, { replace: true, preventScrollReset: true });
  };
  const selectFromWheel = useEffectEvent((index: number) => select(index));
  useEffect(() => {
    const node = viewport.current;
    if (!node || wide) return;
    // URL reload/Back and a resize keep the same page aligned, without motion.
    const align = () => { scrollTarget.current = current.current; node.scrollTo({ left: node.clientWidth * current.current, behavior: 'instant' }); };
    align();
    const observer = new ResizeObserver(align); observer.observe(node);
    // Prevent edge overscroll from carrying momentum into the wrapped page.
    // Ordinary horizontal paging and all vertical scrolling stay native.
    const stopEdgePan = (event: TouchEvent) => {
      const first = event.touches[0], from = touch.current;
      if (!first || !from) return;
      const dx = first.clientX - from.x, dy = first.clientY - from.y;
      if (Math.abs(dx) > 12 && Math.abs(dx) > Math.abs(dy) &&
        (from.index === count - 1 && dx < 0 || from.index === 0 && dx > 0)) event.preventDefault();
    };
    node.addEventListener('touchmove', stopEdgePan, { passive: false });
    // Trackpad swipes arrive as wheel events, without touchstart/touchend.
    // Wrap once per gesture and consume its momentum on the destination page.
    let wheel: { time: number; direction: number; index: number; distance: number; wrapped: boolean } | null = null;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
      const direction = Math.sign(event.deltaX);
      if (!wheel || event.timeStamp - wheel.time > 180 || direction !== wheel.direction) {
        wheel = { time: event.timeStamp, direction, index: current.current, distance: 0, wrapped: false };
      }
      wheel.time = event.timeStamp;
      if (wheel.wrapped) { event.preventDefault(); return; }
      scrollTarget.current = null;
      const atStart = direction < 0 && wheel.index === 0 && node.scrollLeft <= 2;
      const atEnd = direction > 0 && wheel.index === count - 1 && node.scrollLeft >= node.scrollWidth - node.clientWidth - 2;
      if (!atStart && !atEnd) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? node.clientWidth : 1;
      wheel.distance += Math.abs(event.deltaX) * unit;
      if (wheel.distance >= 60) {
        wheel.wrapped = true;
        selectFromWheel(atEnd ? 0 : count - 1);
      }
    };
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => { observer.disconnect(); node.removeEventListener('touchmove', stopEdgePan); node.removeEventListener('wheel', onWheel); };
  }, [count, wide]);
  useLayoutEffect(() => {
    if (!wide && viewport.current && (active !== current.current || count !== previousCount.current || wide !== previousWide.current)) {
      current.current = active;
      scrollTarget.current = active;
      viewport.current.scrollTo({ left: viewport.current.clientWidth * active, behavior: 'instant' });
    }
    previousCount.current = count;
    previousWide.current = wide;
  }, [active, count, wide]);
  const favoritesPath = auth.signedIn ? '/favorites' : '/account';
  return <section className="home-spotlight" aria-label="Гонка, пилоты и команда" aria-roledescription={wide ? undefined : 'карусель'}>
    <div className="home-spotlight-viewport" ref={viewport} tabIndex={wide ? undefined : 0} aria-label="Слайды гонки, пилотов и команды" onKeyDown={event => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); select(active + (event.key === 'ArrowRight' ? 1 : -1)); }
    }} onTouchStart={event => {
      scrollTarget.current = null;
      const first = event.touches[0];
      if (first) touch.current = { x: first.clientX, y: first.clientY, index: current.current };
    }} onTouchEnd={event => {
      const first = event.changedTouches[0], from = touch.current;
      touch.current = null;
      if (!first || !from) return;
      const dx = first.clientX - from.x, dy = first.clientY - from.y;
      if (Math.abs(dx) < 60 || Math.abs(dy) >= Math.abs(dx)) return;
      if (from.index === count - 1 && current.current === count - 1 && dx < 0) select(0);
      else if (from.index === 0 && current.current === 0 && dx > 0) select(count - 1);
    }} onTouchCancel={() => { touch.current = null; }} onScroll={event => {
      const node = event.currentTarget;
      if (wide || !node.clientWidth || !auth.loaded) return;
      // DOM growth after sign-in and snap alignment must not rewrite the intended URL.
      if (scrollTarget.current !== null) {
        const left = scrollTarget.current * node.clientWidth;
        if (Math.abs(node.scrollLeft - left) > 2) node.scrollTo({ left, behavior: 'instant' });
        return;
      }
      const index = Math.max(0, Math.min(count - 1, Math.round(node.scrollLeft / node.clientWidth)));
      if (index !== current.current) { current.current = index; setParams(previous => { const next = new URLSearchParams(previous); if (index) next.set('spotlight', keys[index]); else next.delete('spotlight'); return next; }, { replace: true, preventScrollReset: true }); }
    }}>
      <div className="home-spotlight-slide" role="group" aria-roledescription={wide ? undefined : 'слайд'} aria-label={wide ? 'Ближайшая гонка' : `1 из ${count} — ближайшая гонка`} inert={!wide && active !== 0}>
        <Hero nextRace={hero.nextRace} schedule={hero.schedule} userTz={hero.userTz} loaded={hero.loaded} onRetry={() => void hero.load()} />
      </div>
      {visibleSlots.map((slot, index) => <div key={keys[index + 1]} className="home-spotlight-slide" role="group" aria-roledescription={wide ? undefined : 'слайд'} aria-label={wide ? labels[index + 1] : `${index + 2} из ${count} — ${labels[index + 1]}`} inert={!wide && active !== index + 1}>
        {guest && auth.loaded ? <PersonalizeSlide /> : <FavoriteSlide slot={slot} season={season} loaded={Boolean(data)} failed={Boolean(data?.failed)} favoritesPath={favoritesPath} onRetry={retry} favoritesFailed={Boolean(data?.favoritesFailed)} /> }
      </div>)}
    </div>
    <div className="home-spotlight-controls">
      <button type="button" onClick={() => select(active - 1)} aria-label="Предыдущий слайд"><span className="home-spotlight-prev"><HomeIcon name="chevronRight" /></span></button>
      <div className="home-spotlight-pages" aria-label="Выбрать слайд">{keys.map((key, index) => <button type="button" key={key} onClick={() => select(index)} aria-label={`${index + 1} из ${count}: ${labels[index]}`} aria-current={active === index ? 'true' : undefined}><span /></button>)}</div>
      <button type="button" onClick={() => select(active + 1)} aria-label="Следующий слайд"><HomeIcon name="chevronRight" /></button>
    </div>
    <p className="home-sr-only" hidden={wide} aria-live="polite" aria-atomic="true">{active + 1} из {count}: {labels[active]}</p>

  </section>;
}
