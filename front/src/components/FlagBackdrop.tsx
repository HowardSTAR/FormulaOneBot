import './race-flag-backdrop.css';

/** Render a country code already resolved by a closed country/nationality map. */
export function FlagBackdrop({ code, className = '' }: { code?: string | null; className?: string }) {
  if (!code) return null;
  const base = import.meta.env?.BASE_URL || '/';
  return <span className={`race-flag-backdrop ${className}`} aria-hidden="true" data-country={code}>
    <img src={`${base}flags/${code}.svg`} alt="" width="640" height="480" loading="lazy" decoding="async" />
  </span>;
}
