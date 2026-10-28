import { useEffect, useRef, useState } from 'react';
import { HomeIcon } from '../index/HomeIcon';
import { useMediaQuery } from '../../helpers/useMediaQuery';
import { communityTracks, communityTrackImage, sampleTrack } from './communityTracks';

/** Scenery comes from the game renderer; an unknown track never gets another map. */
export function CommunityTrackPreview({ trackId }: { trackId: string }) {
  const track = communityTracks.find(track => track.id === trackId);
  const [sceneError, setSceneError] = useState(false);
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)');
  const figure = useRef<HTMLElement>(null), car = useRef<SVGGElement>(null);
  const progress = useRef(0);
  const [inView, setInView] = useState(false);
  const [demo, setDemo] = useState<'running' | 'paused'>('running');
  useEffect(() => {
    const element = figure.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!track || reduced || !inView || demo !== 'running') return;
    let frame = 0, previous = 0;
    const update = (now: number) => {
      if (previous && !document.hidden) progress.current = (progress.current + Math.min(now - previous, 80) / 9000) % 1;
      previous = now;
      const point = sampleTrack(track.centerLine, progress.current);
      car.current?.setAttribute('transform', `translate(${point.x} ${point.y}) rotate(${point.heading})`);
      frame = requestAnimationFrame(update);
    };
    frame = requestAnimationFrame(update);
    return () => cancelAnimationFrame(frame);
  }, [track, reduced, inView, demo]);
  if (!track) return <figure className="community-track-unavailable" role="status"><HomeIcon name="race" /><figcaption>Схема этой трассы пока недоступна.</figcaption></figure>;
  const scene = communityTrackImage(track.id);
  const outline = !scene || sceneError;
  const line = [...track.centerLine, track.centerLine[0]].map(point => point.join(',')).join(' ');
  const start = sampleTrack(track.centerLine, 0);
  return <figure className={`community-track-preview${outline ? ' community-track-preview--outline' : ''}`} ref={figure}>
    <svg viewBox="0 0 1536 1024" role="img" aria-label={`Схема трассы ${track.name}`}>
      <image className="community-track-scene" href={scene} width="1536" height="1024" onError={() => setSceneError(true)} style={outline ? { display: 'none' } : undefined} />
      <polyline className="community-track-road" points={line} fill="none" strokeWidth={outline ? track.roadHalfWidth * 2 : 3} strokeDasharray={outline ? undefined : '12 16'} strokeLinejoin="round" />
      <g ref={car} className="community-demo-car" transform={`translate(${start.x} ${start.y}) rotate(${start.heading})`}>
        <image href={`${import.meta.env.BASE_URL}race-game/assets/open-wheel-car.png`} x="-26" y="-52" width="52" height="78" />
      </g>
    </svg>
    <figcaption><span>{track.format}</span>{!reduced && <button type="button" className="community-demo-control" aria-label={demo === 'running' ? 'Пауза демонстрации трассы' : 'Продолжить демонстрацию трассы'} onClick={() => {
      setDemo(value => value === 'running' ? 'paused' : 'running');
    }}><HomeIcon name={demo === 'running' ? 'pause' : 'play'} /><span>{demo === 'running' ? 'Пауза' : 'Продолжить'}</span></button>}</figcaption>
  </figure>;
}
