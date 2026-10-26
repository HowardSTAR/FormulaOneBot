import { useState } from 'react';
import { teamLogoUrl } from '../helpers/f1Assets';
import { homeTeamIdentity } from '../pages/index/team-identity';
import { spotlightTeamMedia } from '../pages/index/spotlight-team-media';
import { teamLogoBounds } from '../helpers/teamLogoBounds';
import './team-logo.css';

export function TeamLogo({ name, season, id = '' }: { name: string; season: number; id?: string }) {
  const [index, setIndex] = useState(0);
  const media = spotlightTeamMedia(id, name, season);
  const sources = [...media.logo, teamLogoUrl(id, name, season)];
  const bounds = index === 0 && media.logo.length ? teamLogoBounds[homeTeamIdentity(id, name)] : undefined;
  const initials = name.split(/\s+/).map(word => word[0]).join('').slice(0, 3);
  const image = index < sources.length ? <img src={sources[index]} alt="" width={480} height={480} loading="lazy" decoding="async" onError={() => setIndex(value => value + 1)} /> : null;
  if (!image) return <span className="team-logo" aria-hidden="true"><span className="team-logo-fallback">{initials}</span></span>;
  if (!bounds) return <span className="team-logo" aria-hidden="true">{image}</span>;
  const [left, top, right, bottom] = bounds;
  const width = right - left, height = bottom - top;
  const round = Math.abs(width / height - 1) < .1;
  const scale = Math.min((round ? 28 : 34) / width, (round ? 28 : 30) / height);
  return <span className="team-logo" aria-hidden="true">
    <span className="team-logo-art" style={{ width: `${width * scale / 16}rem`, height: `${height * scale / 16}rem` }}>
      <span style={{ position: 'absolute', width: `${480 / width * 100}%`, height: `${480 / height * 100}%`, left: `${-left / width * 100}%`, top: `${-top / height * 100}%` }}>{image}</span>
    </span>
  </span>;
}
