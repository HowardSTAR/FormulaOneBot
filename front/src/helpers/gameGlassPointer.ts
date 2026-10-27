import type { PointerEvent } from 'react';

export function moveGameGlass(event: PointerEvent<HTMLDivElement>) {
  if (!(event.target instanceof Element)) return;
  const control = event.target.closest<HTMLElement>('.reaction-button, .reflex-tile, .reaction-light');
  if (!control) return;
  const rect = control.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  control.style.setProperty('--glass-x', `${(event.clientX - rect.left) / rect.width * 100}%`);
  control.style.setProperty('--glass-y', `${(event.clientY - rect.top) / rect.height * 100}%`);
  control.dataset.glassHover = 'true';
}

export function leaveGameGlass(event: PointerEvent<HTMLDivElement>) {
  event.currentTarget.querySelectorAll<HTMLElement>('[data-glass-hover]').forEach(control => {
    control.style.removeProperty('--glass-x');
    control.style.removeProperty('--glass-y');
    delete control.dataset.glassHover;
  });
}
