// Fictional, local-only profile scenarios. Never imported by production routes.
export function profilePreview(query: URLSearchParams) {
  const member = ['member', 'linked'].includes(query.get('auth') || '');
  const visitor = query.get('owner') === '0';
  const owner = member && !visitor;
  const state = query.get('state');
  let failures = state === 'account-profile-error' ? 1 : 0;
  let saveFailures = state === 'profile-save-error' ? 1 : 0;
  let badge: unknown = null;
  let avatar = { helmet: 'scarlet', suit: 'scarlet', background: 'garage' };
  let style = { frame: 'red', color: 'white', background: 'scarlet' };
  const empty = state === 'account-profile-empty';
  const supporter = query.get('tier') !== '0';
  const families = ['oracle', 'podium', 'rhythm', 'lights', 'ghost', 'atlas', 'grid', 'heart'].map((id, index) => ({
    id, name: ['Оракул паддока', 'Идеальная тройка', 'В ритме сезона', 'Пять огней', 'Быстрее своей тени', 'Без границ', 'Дирижёр сетки', 'Сердце проекта'][index],
    group: index === 4 ? 'Гонка' : 'Прогнозы',
    levels: ['Бронза', 'Серебро', 'Золото'].map((tier, level) => ({
      id: `${id}:0:${level}`, level, tier, season: 0, target: [3, 12, 24][level], progress: 8,
      condition: `Сделать ${[3, 12, 24][level]} успешных прогнозов.`,
      rule: 'В этом демо показаны вымышленные достижения.',
      earned_at: !empty && level === 0 && index < 3 ? '2026-10-11 12:00:00' : null,
    })).filter(level => owner || level.earned_at),
  })).filter(family => family.levels.length);
  const earned = families.flatMap(family => family.levels.filter(level => level.earned_at).map(level => ({ ...level, family: family.id, name: family.name })));
  return async (url: URL, init?: RequestInit): Promise<Response | null> => {
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
    if (url.pathname === '/api/account/boosty') return json({ configured: true, active: supporter, premium_active: supporter, can_check: true });
    if (!url.pathname.startsWith('/api/profiles/')) return null;
    if (url.pathname.endsWith('/avatar/v1.png')) return fetch(new URL('./profile-avatar.png', import.meta.url));
    if (url.pathname === '/api/profiles/me/avatar' || url.pathname === '/api/profiles/me/style' || url.pathname === '/api/profiles/me/trophy-badge') {
      if (!owner) return json({ detail: 'Необходим вход' }, 401);
      if (saveFailures-- > 0) return json({ detail: 'Не удалось сохранить. Повторите попытку.' }, 503);
      const body = JSON.parse(String(init?.body));
      if (url.pathname.endsWith('/avatar')) avatar = body;
      if (url.pathname.endsWith('/style')) style = body;
      if (url.pathname.endsWith('/trophy-badge')) badge = earned.find(award => award.id === body.id) || null;
      return json({ saved: true });
    }
    if (url.pathname.endsWith('/trophies')) return json({ user_id: 1, season: 2026, calendar_known: true, season_closed: false, earned, pending: [], families, badge });
    if (url.pathname === '/api/profiles/supporters') return json({ season: 2026, current_user_id: 1, entries: empty ? [] : [
      { user_id: 2, display_name: 'Apex Hunter', tier_name: 'Полный газ', place: 1, total_points: 204, rounds_scored: 12, wins: 3, best_points: 38 },
      { user_id: 1, display_name: 'Turbo Racer', tier_name: 'Полный газ', place: 2, total_points: 186, rounds_scored: 12, wins: 2, best_points: 36 },
    ] });
    if (!member && !visitor) return json({ detail: 'Необходим вход' }, 401);
    if (failures-- > 0) return json({ detail: 'Не удалось загрузить профиль. Попробуйте ещё раз.' }, 503);
    if (state === 'account-profile-loading') return new Promise<Response>(() => {});
    const season = Number(url.searchParams.get('season') || 2026);
    const predictions = empty ? [] : ['Гран-при Японии', 'Гран-при Австралии', 'Гран-при Китая'].map((event_name, index) => ({
      round: index + 1, event_name, points: 36 - index * 6, max_points: 40,
      winner_driver: 'NOR', second_driver: 'VER', third_driver: 'PIA', fourth_driver: 'LEC', fifth_driver: 'RUS', pole_driver: 'NOR',
      fastest_lap_driver: 'VER', first_retirement_driver: 'HUL', safety_car: 1, sprint_pole_driver: null, sprint_winner_driver: null,
    }));
    return json({ user_id: 1, display_name: query.get('name') || 'Turbo Racer', is_owner: owner, profile_guide_seen: true,
      email: 'racer@example.com', email_verified: state !== 'profile-unverified', tier: supporter ? 3 : 0, tier_name: supporter ? 'Полный газ' : 'Участник', supporter,
      avatar, style, avatar_options: { helmet: { scarlet: 'Алый / полоса', cobalt: 'Кобальт / двойная полоса', mint: 'Жемчуг / мята' }, suit: { scarlet: 'Алый / графит', cobalt: 'Индиго / лайм', mint: 'Графит / мята' }, background: { garage: 'Ночной бокс', scarlet: 'Красный сектор', cobalt: 'Синий час', mint: 'Полярное сияние', gold: 'Золотой подиум' } },
      options: { frame: { classic: 0, red: 2, silver: 2, gold: 3, neon: 3 }, color: { white: 0, red: 2, blue: 2, gold: 3, mint: 3 }, background: { carbon: 0, grid: 2, scarlet: 2, aurora: 3, champion: 3 } },
      season, seasons: [2026, 2025], total_points: empty ? 0 : 186, scored_rounds: empty ? 0 : 12, best_prediction: predictions[0] || null, predictions,
      records: empty ? [] : [{ track_id: 'emerald-loop-v2', track_name: 'Emerald Loop', best_time_ms: 98432, attempts: 12 }],
      favorites: empty ? { drivers: [], teams: [] } : { drivers: ['NOR', 'LEC'], teams: ['McLaren'] },
    });
  };
}
