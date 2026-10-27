import { initializeTheme, getTheme, setTheme, subscribeTheme } from '../../front/src/helpers/theme';

export function initializeGameTheme() {
  initializeTheme();
  const buttons = document.querySelectorAll<HTMLButtonElement>('[data-game-theme]');
  const update = () => {
    const dark = getTheme() === 'dark';
    buttons.forEach(button => {
      button.setAttribute('aria-label', `Включить ${dark ? 'светлую' : 'тёмную'} тему`);
      button.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${dark ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>' : '<path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>'}</svg>`;
    });
  };
  subscribeTheme(update);
  update();
  buttons.forEach(button => button.addEventListener('click', () => setTheme(getTheme() === 'dark' ? 'light' : 'dark')));
}
