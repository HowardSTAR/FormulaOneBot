import './race-flag-backdrop.css';

/** Render a country code already resolved by a closed country/nationality map. */
export function FlagBackdrop({ code, className = '', fit = 'cover' }: { code?: string | null; className?: string; fit?: 'cover' | 'stretch' }) {
  if (!code) return null;
  const base = import.meta.env?.BASE_URL || '/';
  const source = `${base}flags/${code}.svg`;
  return <span className={`race-flag-backdrop ${className}`} aria-hidden="true" data-country={code}>
    {fit === 'stretch' ? <svg viewBox="0 0 640 480" preserveAspectRatio="none" focusable="false"><image href={source} width="640" height="480" preserveAspectRatio="none" /></svg>
      : <img src={source} alt="" width="640" height="480" loading="lazy" decoding="async" />}
  </span>;
}
