// Isolated browser preview; no production requests or records are changed.
export function gamesPreview(query: URLSearchParams) {
  let profile = { display_name: 'Alex', participate: false, prompt_seen: query.get('state') !== 'games-onboarding' && query.get('state') !== 'games-save-error' };
  let saveFailures = query.get('state') === 'games-save-error' ? 1 : 0;
  let leaderboardFailures = query.get('state') === 'games-error' ? 1 : 0;
  const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  return async (url: URL, init?: RequestInit) => {
    if (url.pathname === '/api/reaction-leaderboard/profile') {
      if (query.get('auth') !== 'member') return json({ detail: 'Войдите в аккаунт.' }, 401);
      if (init?.method === 'POST') {
        if (saveFailures-- > 0) return json({ detail: 'Не удалось сохранить настройки. Повторите попытку.' }, 503);
        profile = JSON.parse(String(init.body));
        return json({ profile });
      }
      return json(profile);
    }
    if (['/api/reaction-leaderboard', '/api/reflex-grid-leaderboard', '/api/race-game-leaderboard'].includes(url.pathname)) {
      if (query.get('state') === 'games-loading') await new Promise(resolve => setTimeout(resolve, 2000));
      if (leaderboardFailures-- > 0) return json({ detail: 'Не удалось загрузить результаты.' }, 503);
      const entries = query.get('state') === 'games-empty' ? [] : ['Марина', 'Alex', 'Очень длинное игровое имя в рейтинге'].map((name, index) => ({ place: index + 1, telegram_id: index + 1, name, time_ms: 185 + index * 35, score: 24 - index, is_me: index === 1, laps: 3, track_id: 'emerald-loop-v1' }));
      return json({ entries, me: query.get('auth') === 'member' ? entries[1] ?? null : null });
    }
    if (['/api/reaction-leaderboard/score', '/api/reflex-grid-leaderboard/score'].includes(url.pathname)) return json({ status: 'ok', saved: true });
    return null;
  };
}
