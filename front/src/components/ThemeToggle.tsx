import { useSyncExternalStore } from 'react';
import { getTheme, setTheme, subscribeTheme } from '../helpers/theme';

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => 'light');
  const target = theme === 'dark' ? 'light' : 'dark';
  const label = target === 'dark' ? 'Тёмная тема' : 'Светлая тема';
  return <button type="button" className="theme-toggle" onClick={() => setTheme(target)} aria-label={`Включить: ${label}`} title={`Включить: ${label}`}>
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {target === 'dark' ? <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" /> : <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></>}
    </svg>
  </button>;
}
