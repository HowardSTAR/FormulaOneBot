import { useState } from 'react';
import { apiAssetUrl } from '../helpers/api';
import './driver-portrait.css';

export function DriverPortrait({ code = '', name, season, src, className = '' }: { code?: string; name: string; season: number; src?: string; className?: string }) {
  const [index, setIndex] = useState(0);
  const identity = code.toUpperCase();
  const sources = [...new Set([
    src,
    ...(/^[A-Z]{3}$/.test(identity) ? [apiAssetUrl(`/assets/${season}/pilots/${identity}.webp`)] : []),
    apiAssetUrl('/api/pilot-portrait', { code, name, season, strict: true }),
  ].filter((source): source is string => Boolean(source)))];
  return <span className={`entrant-portrait ${className}`} aria-hidden="true">
    {index < sources.length ? <img src={sources[index]} alt="" width={64} height={72} loading="lazy" decoding="async" onError={() => setIndex(value => value + 1)} /> : <span>{code || '—'}</span>}
  </span>;
}
