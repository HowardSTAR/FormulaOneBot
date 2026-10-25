import { raceCountryCode } from '../helpers/raceCountry';
import './race-flag-backdrop.css';

/** Decorative only: the surrounding heading remains the source of event identity. */
export function RaceFlagBackdrop({ country, eventName, className = '' }: {
  country?: string; eventName?: string; className?: string;
}) {
  const code = raceCountryCode(country, eventName);
  if (!code) return null;
  const base = import.meta.env?.BASE_URL || '/';
  return <span className={`race-flag-backdrop ${className}`} aria-hidden="true" data-country={code}>
    <img src={`${base}flags/${code}.svg`} alt="" width="640" height="480" loading="lazy" decoding="async" />
  </span>;
}
