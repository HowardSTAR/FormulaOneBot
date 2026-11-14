// Isolated visual proposal using the production router and demo fixtures.
import './navigation-preview.css';
document.documentElement.classList.add('navigation-preview');
const url = new URL(window.location.href);
for (const [key, value] of Object.entries({ page: 'predictions', tab: 'leaderboard', state: 'production-layout', theme: 'dark', auth: 'linked' })) {
  if (!url.searchParams.has(key)) url.searchParams.set(key, value);
}
window.history.replaceState(null, '', url);
await import('./home-design-preview');
export {};
