import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useLayoutEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import { BackButton } from './BackButton';
import { GlassSwitch } from '../pages/index/GlassSwitch';
import { entrantValue } from '../helpers/entrantPresentation';
import '../pages/index/home-controls.css';
import './entrant-details.css';
import '../pages/index/home-team-colors.css';

export function EntrantStat({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div className="entrant-stat"><dt>{label}</dt><dd>{entrantValue(value)}</dd></div>;
}

type StatIconName = 'win' | 'podium' | 'grid' | 'title' | 'finish';
function StatIcon({ name }: { name: StatIconName }) {
  return <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    {name === 'win' || name === 'title' ? <><path d="M8 3h8v6a4 4 0 0 1-8 0V3Zm0 2H4v2a4 4 0 0 0 4 4m8-6h4v2a4 4 0 0 1-4 4M12 13v5m-4 3v-3h8v3" />{name === 'title' && <path d="M10 7h4m-2-2v4" />}</> : name === 'podium' ? <><path d="M8 21V9h8v12M2 21v-8h6m8 3h6v5M2 21h20" /><path d="M12 3v3" /></> : name === 'grid' ? <><rect x="3" y="3" width="6" height="6" rx="1" /><rect x="15" y="3" width="6" height="6" rx="1" /><rect x="3" y="15" width="6" height="6" rx="1" /><path d="m15 18 2 2 4-5" /></> : <><path d="M5 21V3m0 1h14l-3 4 3 4H5" /><path d="M9 4v8m5-8v8M5 8h12" /></>}
  </svg>;
}

export function EntrantMetric({ label, value, icon, tone = 'team', total }: { label: string; value: string | number; icon: StatIconName; tone?: 'team' | 'gold' | 'blue'; total?: number }) {
  const ratio = typeof value === 'number' && total != null && total > 0 && value >= 0 && value <= total ? value / total : null;
  return <div className="entrant-metric" data-tone={tone} data-missing={typeof value !== 'number' || undefined}>
    <dt><StatIcon name={icon} /><span>{label}</span></dt>
    <dd>{entrantValue(value)}</dd>
    {ratio != null && <dd className="entrant-metric-share"><span className="entrant-metric-track" aria-hidden="true"><span style={{ '--entrant-share': `${ratio * 100}%` } as CSSProperties} /></span><span>{new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 0 }).format(ratio)} гонок</span></dd>}
  </div>;
}

export function EntrantRecord({ label, record, available = true }: { label: string; record: { position: string | number; count: number }; available?: boolean }) {
  const known = available && Number(record.position) > 0;
  return <div className="entrant-record"><dt>{label}</dt><dd>{known ? <><strong>P{record.position}</strong>{record.count > 0 && <span>{entrantValue(record.count)} {new Intl.PluralRules('ru').select(record.count) === 'few' ? 'раза' : 'раз'}</span>}</> : <span>{available ? '—' : 'Нет данных'}</span>}</dd></div>;
}

/** Reserve only the height needed to keep the current scroll position when a
 * shorter panel opens. A long biography must not leave a permanent blank area. */
export function EntrantPanels({ children }: { children: ReactNode }) {
  const frame = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const outer = frame.current, inner = content.current;
    if (!outer || !inner) return;
    let hasReservedSpace = false;
    const measure = () => {
      const box = inner.getBoundingClientRect();
      const otherHeight = document.documentElement.scrollHeight - outer.getBoundingClientRect().height;
      const floor = Math.max(box.height, window.scrollY + window.innerHeight - otherHeight);
      hasReservedSpace = floor > box.height + 1;
      outer.style.minHeight = `${floor}px`;
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(inner);
    const releaseSpace = () => { if (hasReservedSpace) measure(); };
    window.addEventListener('scroll', releaseSpace, { passive: true });
    return () => { observer.disconnect(); window.removeEventListener('scroll', releaseSpace); };
  }, []);
  return <div className="entrant-panels" ref={frame}><div ref={content}>{children}</div></div>;
}

export function EntrantNavigation({ to, label }: { to: string; label: string }) {
  return <nav className="entrant-navigation" aria-label="Навигация карточки">
    <BackButton fallback={to} className="entrant-back" />
    <Link to={to}>{label}</Link>
  </nav>;
}

export function EntrantSections({ biographyLabel = 'Биография' }: { biographyLabel?: string }) {
  const [params] = useSearchParams();
  const { pathname, key } = useLocation();
  const scrollBookmark = useRef<number | null>(null);
  useLayoutEffect(() => {
    const top = scrollBookmark.current;
    scrollBookmark.current = null;
    if (top != null) window.scrollTo({ top, behavior: 'instant' });
  }, [key]);
  const selected = params.get('tab') === 'bio' ? 'bio' : 'stats';
  const destination = (tab: string) => {
    const next = new URLSearchParams(params);
    if (tab === 'stats') next.delete('tab'); else next.set('tab', tab);
    return `${pathname}?${next}`;
  };
  return <div className="entrant-section-control" onPointerDownCapture={() => { scrollBookmark.current = window.scrollY; }} onClickCapture={event => {
    if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) scrollBookmark.current = window.scrollY;
  }}><GlassSwitch className="entrant-sections" label="Разделы карточки" selected={selected} replace items={[
    { id: 'stats', label: 'Статистика', to: destination('stats') },
    { id: 'bio', label: biographyLabel, to: destination('bio') },
  ]} /></div>;
}

export function EntrantLoading({ label }: { label: string }) {
  return <div className="entrant-loading" role="status"><span className="spinner" aria-hidden="true" /><p>{label}…</p></div>;
}
