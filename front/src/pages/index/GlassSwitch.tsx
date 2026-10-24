import { useRef, useState, type CSSProperties } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { HomeIcon, type HomeIconName } from './HomeIcon';
import './glass-switch.css';

export type GlassSwitchItem = { id: string; label: string; to: string; icon?: HomeIconName; state?: unknown };
export function GlassSwitch({ items, selected: active, label, className }: { items: readonly GlassSwitchItem[]; selected: string; label: string; className: string }) {
  const navigate = useNavigate();
  const selected = items.findIndex(item => item.id === active);
  const [position, setPosition] = useState<number | null>(null);
  const drag = useRef<{ id: number; x: number; y: number; center: number; step: number; moved: boolean; position: number } | null>(null);
  const suppressClickUntil = useRef(0);
  const highlighted = position === null ? selected : Math.round(position);
  return <nav className={`home-glass-switch ${className}`} aria-label={label} style={{ '--section-position': position ?? selected, '--section-count': items.length } as CSSProperties} data-dragging={position !== null || undefined}
    onPointerDown={event => {
      if (!event.isPrimary || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const links = event.currentTarget.querySelectorAll('a');
      const first = links[0].getBoundingClientRect(), second = links[1].getBoundingClientRect();
      suppressClickUntil.current = 0;
      drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, center: first.left + first.width / 2, step: second.left - first.left, moved: false, position: selected };
    }} onPointerMove={event => {
      const gesture = drag.current;
      if (!gesture || gesture.id !== event.pointerId) return;
      const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
      if (!gesture.moved) {
        if (Math.abs(dx) < 6 || Math.abs(dy) > Math.abs(dx)) return;
        gesture.moved = true;
        event.currentTarget.setPointerCapture(event.pointerId);
      }
      gesture.position = Math.max(0, Math.min(items.length - 1, (event.clientX - gesture.center) / gesture.step));
      setPosition(gesture.position);
    }} onPointerUp={event => {
      const gesture = drag.current;
      drag.current = null;
      setPosition(null);
      if (!gesture || gesture.id !== event.pointerId || !gesture.moved) return;
      suppressClickUntil.current = performance.now() + 350;
      const destination = items[Math.round(gesture.position)];
      navigate(destination.to, { preventScrollReset: true, state: destination.state });
    }} onPointerCancel={() => { drag.current = null; setPosition(null); }} onLostPointerCapture={event => { if (event.target === event.currentTarget) { drag.current = null; setPosition(null); } }}
    onClickCapture={event => { if (event.detail > 0 && performance.now() < suppressClickUntil.current) { event.preventDefault(); event.stopPropagation(); } }}>
    <span className="home-section-light" aria-hidden="true" />
    <span className="home-section-lens" aria-hidden="true" />
    {items.map((item, index) => <Link key={item.id} to={item.to} state={item.state} draggable={false} preventScrollReset aria-label={item.label} title={item.label} aria-current={active === item.id ? 'page' : undefined} data-highlighted={highlighted === index || undefined}>{item.icon ? <HomeIcon name={item.icon} /> : <span>{item.label}</span>}</Link>)}
  </nav>;
}
