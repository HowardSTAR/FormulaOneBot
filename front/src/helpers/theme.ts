export type Theme = 'light' | 'dark';
export const THEME_KEY = 'turbotears-theme';

export function storedTheme(storage: Pick<Storage, 'getItem'>): Theme | null {
  try {
    const value = storage.getItem(THEME_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch { return null; }
}

export function resolveTheme(preference: Theme | null, systemDark: boolean): Theme {
  return preference ?? (systemDark ? 'dark' : 'light');
}

let theme: Theme = 'light';
let preference: Theme | null = null;
let initialized = false;
const listeners = new Set<() => void>();

function applyTheme(value: Theme) {
  theme = value;
  document.documentElement.dataset.theme = value;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', value === 'dark' ? '#141518' : '#f5f5f7');
  listeners.forEach(listener => listener());
}

export function initializeTheme() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  // Access to localStorage itself can throw in private or embedded browsers.
  try { preference = storedTheme(window.localStorage); } catch { preference = null; }
  applyTheme(resolveTheme(preference, system.matches));
  system.addEventListener('change', () => {
    if (!preference) applyTheme(resolveTheme(null, system.matches));
  });
  window.addEventListener('storage', event => {
    if (event.key !== THEME_KEY && event.key !== null) return;
    try { preference = storedTheme(window.localStorage); } catch { preference = null; }
    applyTheme(resolveTheme(preference, system.matches));
  });
}

export function setTheme(value: Theme) {
  initializeTheme();
  preference = value;
  try { window.localStorage.setItem(THEME_KEY, value); } catch { /* Preserve the choice for this session. */ }
  applyTheme(value);
}

export function subscribeTheme(listener: () => void) {
  initializeTheme();
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export const getTheme = () => theme;
