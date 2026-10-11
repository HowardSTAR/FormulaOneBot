import './supporter-badge.css';

/** Entitlement comes from the server; the badge never grants subscription rights. */
export default function SupporterBadge({ tierName, large = false }: { tierName?: string; large?: boolean }) {
  const label = `Подписчик TurboTears${tierName ? ` · ${tierName}` : ''}`;
  return <span className={`supporter-badge${large ? ' supporter-badge-large' : ''}`} role="img" aria-label={label} title={label}>
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path className="supporter-badge-shield" d="m16 2 12 7v14l-12 7-12-7V9Z" />
      <path className="supporter-badge-rim" d="m16 5 9 5v12l-9 5-9-5V10Z" />
      <path className="supporter-badge-speed" d="M10 11h6l-3 5h5l-8 8 3-7H8Zm9 0h5l-3 5h-5Z" />
    </svg>
  </span>;
}
