import { useState } from 'react';
import { apiAssetUrl } from '../helpers/api';
import './driver-portrait.css';

function PortraitImage({ sources, code }: { sources: string[]; code: string }) {
  const [index, setIndex] = useState(0);
  return index < sources.length ? <img src={sources[index]} alt="" width={64} height={72} loading="lazy" decoding="async"
    onLoad={event => { const image = event.currentTarget; image.dataset.fullBody = String(image.naturalHeight / image.naturalWidth > 2); }}
    onError={() => setIndex(value => value + 1)} /> : <span>{code || '—'}</span>;
}

export function DriverPortrait({ code = '', name, season, src, className = '' }: { code?: string; name: string; season: number; src?: string; className?: string }) {
  const identity = code.toUpperCase();
  const sources = [...new Set([
    // The API's headshot is a small face crop. Prefer the season's original
    // full-body artwork before applying the shared waist-up framing.
    ...(/^[A-Z]{3}$/.test(identity) ? [apiAssetUrl(`/assets/${season}/pilots/${identity}.webp`)] : []),
    src,
    apiAssetUrl('/api/pilot-portrait', { code, name, season, strict: true }),
  ].filter((source): source is string => Boolean(source)))];
  return <span className={`entrant-portrait ${className}`} aria-hidden="true">
    <PortraitImage key={sources.join('|')} sources={sources} code={code} />
  </span>;
}
