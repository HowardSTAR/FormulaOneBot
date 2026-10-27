// Isolated router-boundary preview. No production APIs or account data are used.
import { createRoot } from 'react-dom/client';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { RouteErrorPage } from '../src/components/RouteErrorPage';
import { initializeTheme, setTheme, storedTheme } from '../src/helpers/theme';
await import('../src/App');
const query = new URLSearchParams(location.search);
initializeTheme();
const theme = query.get('theme');
if ((theme === 'light' || theme === 'dark') && !storedTheme(localStorage)) setTheme(theme);
if (query.get('scale') === '2') document.documentElement.style.fontSize = '200%';
const receipt = 'route-recovery-preview-retried';
const router = createMemoryRouter([{
  path: '/unavailable',
  loader: () => {
    if (query.get('retry') === 'success' && sessionStorage.getItem(receipt)) return null;
    if (query.get('retry') === 'success') sessionStorage.setItem(receipt, '1');
    if (query.get('state') === 'not-found') throw new Response('Private diagnostic', { status: 404 });
    if (query.get('state') === 'chunk') throw new TypeError('Failed to fetch dynamically imported module: internal-preview-module');
    throw new Error('Private diagnostic: illustrative render failure');
  },
  errorElement: <RouteErrorPage />,
  element: <main style={{ padding: 32 }}><h1>Страница открыта</h1><p>Демо: повторная загрузка завершилась успешно.</p></main>,
}], { initialEntries: ['/unavailable?season=2026&round=19'] });
createRoot(document.getElementById('root')!).render(<RouterProvider router={router} />);
const note = document.createElement('aside');
note.textContent = 'Демо · ошибка смоделирована локально';
note.style.cssText = 'padding:6px 16px;text-align:center;font:12px/1.5 system-ui;background:#faeeec;color:#78221d';
document.body.prepend(note);
