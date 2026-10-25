import { useEffect, useLayoutEffect, useState } from 'react';
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
import { useCircularSpotlight } from './useCircularSpotlight';
import { homeTeamIdentity } from './team-identity';

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
  return <section className={`home-favorite-card${team ? ' home-favorite-card--team' : ''}`} aria-label={entry.name} data-team={homeTeamIdentity(entry.constructorId || '', teamName)}>
    {team && <span className="home-team-logo" aria-hidden="true"><MediaImage key={media.logo[0]} sources={media.logo} className="home-team-logo-image" fallback={entry.name.slice(0, 3).toUpperCase()} /></span>}
    <div className={team ? 'home-team-car' : 'home-favorite-watermark'} aria-hidden="true"><MediaImage key={media.logo[0]} sources={team ? media.car : media.logo} className="home-team-backdrop-image" /></div>
    <div className="home-favorite-copy">
      <div className="home-favorite-kind"><HomeIcon name={favorite ? 'favorite' : team ? 'teams' : 'drivers'} /><span>{favorite ? team ? 'Избранная команда' : 'Избранный пилот' : team ? 'Лидер среди команд' : 'В лидерах сезона'}</span></div>
      <div className="home-favorite-identity"><h2>{entry.name}</h2></div>
      <p className="home-favorite-team">{team ? 'Кубок конструкторов' : entry.constructorName || `Сезон ${season}`}</p>
      <dl className="home-favorite-stats"><div><dt>Очки</dt><dd>{points?.toLocaleString('ru-RU') ?? '—'}</dd></div><div><dt>Место</dt><dd>{position && position > 0 ? position : '—'}</dd></div></dl>
      {favoritesFailed && <div className="home-favorite-error" role="status">Избранное не загрузилось. Показаны лидеры. <button type="button" className="home-glass-button" onClick={onRetry}>Повторить</button></div>}
    </div>
    {!team && <SpotlightImage key={src} src={src} fallback={entry.number || entry.code || entry.name.slice(0, 3)} />}
    <Link className="home-favorite-name home-favorite-open" to={details} aria-label={`${team ? 'О команде' : 'О пилоте'}: ${entry.name}`} />
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
  const keys = auth.signedIn ? memberKeys : memberKeys.slice(0, 2);
  const count = keys.length;
  const requested = params.get('spotlight') || 'race';
  const active = Math.max(0, keys.indexOf(requested));
  const slots = spotlightSlots(data?.drivers || [], data?.teams || [], data?.favorites || { drivers: [], teams: [] });
  const guest = !auth.signedIn;
  const visibleSlots = guest ? slots.slice(0, 1) : slots;
  const labels = ['Ближайшая гонка', ...visibleSlots.map((slot, i) => guest ? 'Персонализировать главную' : slot.entry?.name || (i === 2 ? 'Команда' : `Пилот ${i + 1}`))];
  useEffect(() => {
    if (auth.loaded && !auth.signedIn && requested !== 'race' && requested !== 'driver-1') {
      setParams(previous => { const next = new URLSearchParams(previous); next.set('spotlight', 'driver-1'); return next; }, { replace: true, preventScrollReset: true });
    }
  }, [auth.loaded, auth.signedIn, requested, setParams]);
  const { viewport, select } = useCircularSpotlight(count, active, wide, index => {
    setParams(previous => { const next = new URLSearchParams(previous); if (index) next.set('spotlight', keys[index]); else next.delete('spotlight'); return next; }, { replace: true, preventScrollReset: true });
  });
  useLayoutEffect(() => {
    if (!wide || !auth.signedIn) return;
    const team = viewport.current?.querySelector<HTMLElement>('[data-slide-index="3"]');
    const screen = viewport.current?.closest<HTMLElement>('.home-screen');
    if (!team || !screen) return;
    // Anchor the personal column below the actual team height, independent of details.
    const measure = () => screen.style.setProperty('--home-team-height', `${team.getBoundingClientRect().height}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(team);
    return () => { observer.disconnect(); screen.style.removeProperty('--home-team-height'); };
  }, [wide, auth.signedIn, viewport]);
  const favoritesPath = auth.signedIn ? '/favorites' : '/account';
  return <section className="home-spotlight" aria-label="Гонка, пилоты и команда" aria-roledescription={wide ? undefined : 'карусель'}>
    <div className="home-spotlight-viewport" ref={viewport} tabIndex={wide ? undefined : 0} aria-label="Слайды гонки, пилотов и команды" onKeyDown={event => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); select(active + (event.key === 'ArrowRight' ? 1 : -1)); }
    }}>
      <div className="home-spotlight-buffer" aria-hidden="true" inert />
      <div className="home-spotlight-slide" data-slide-index="0" role="group" aria-roledescription={wide ? undefined : 'слайд'} aria-label={wide ? 'Ближайшая гонка' : `1 из ${count} — ближайшая гонка`} inert={!wide && active !== 0}>
        <Hero nextRace={hero.nextRace} schedule={hero.schedule} userTz={hero.userTz} loaded={hero.loaded} onRetry={() => void hero.load()} />
      </div>
      {visibleSlots.map((slot, index) => <div key={keys[index + 1]} className="home-spotlight-slide" data-slide-index={index + 1} role="group" aria-roledescription={wide ? undefined : 'слайд'} aria-label={wide ? labels[index + 1] : `${index + 2} из ${count} — ${labels[index + 1]}`} inert={!wide && active !== index + 1}>
        {guest && auth.loaded ? <PersonalizeSlide /> : <FavoriteSlide slot={slot} season={season} loaded={Boolean(data)} failed={Boolean(data?.failed)} favoritesPath={favoritesPath} onRetry={retry} favoritesFailed={Boolean(data?.favoritesFailed)} /> }
      </div>)}
      <div className="home-spotlight-buffer" aria-hidden="true" inert />
    </div>
    <div className="home-spotlight-controls">
      <div className="home-spotlight-pages" aria-label="Выбрать слайд">{keys.map((key, index) => <button type="button" key={key} onClick={() => select(index)} aria-label={`${index + 1} из ${count}: ${labels[index]}`} aria-current={active === index ? 'true' : undefined}><span /></button>)}</div>
    </div>
    <p className="home-sr-only" hidden={wide} aria-live="polite" aria-atomic="true">{active + 1} из {count}: {labels[active]}</p>

  </section>;
}
