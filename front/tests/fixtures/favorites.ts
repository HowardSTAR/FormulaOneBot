// Development-only in-memory favorites; never writes to a backend.
export function favoritesPreview(query: URLSearchParams) {
  const state = query.get('state');
  const favorites = state === 'favorites-empty' ? { drivers: [] as string[], teams: [] as string[] }
    : state === 'favorites-missing' ? { drivers: ['OLD'], teams: ['Old Team'] }
    : { drivers: ['PIA', 'NOR', 'VER'], teams: ['McLaren', 'Ferrari'] };
  let home = { drivers: favorites.drivers.slice(0, 2), teams: favorites.teams.slice(0, 1) };
  return (url: URL, init?: RequestInit) => {
    if (!url.pathname.startsWith('/api/favorites')) return null;
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
    if (state === 'favorites-error') return json({}, 503);
    if (init?.method === 'POST') {
      if (state === 'favorites-save-error') return json({}, 503);
      const body = JSON.parse(String(init.body));
      if (url.pathname === '/api/favorites/home') home = body;
      else {
        const kind = url.pathname.endsWith('/driver') ? 'drivers' : 'teams';
        favorites[kind] = favorites[kind].includes(body.id) ? favorites[kind].filter(value => value !== body.id) : [...favorites[kind], body.id];
      }
    }
    return json({ ...favorites, home });
  };
}
