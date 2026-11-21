// Isolated design preview. No admin request or mutation reaches the backend.
export function adminPreview(query: URLSearchParams) {
  let failures = query.get('state') === 'admin-error' ? 1 : 0;
  let reportFailures = query.get('state') === 'analytics-error' ? 1 : 0;
  let saveFailures = query.get('state') === 'admin-save-error' ? 1 : 0;
  let email = 'alex@example.test';
  const empty = query.get('state') === 'admin-empty';
  const stage = { season: 2026, round: 19, event_name: 'Гран-при США', missing: ['safety_car'] };
  const history = [
    { id: 71, action: 'user.role_changed', created_at: '2026-11-01T09:00:00Z', target_user_id: 42, actor_user_id: 1, actor_email: 'admin@example.test', actor_telegram_id: null, details: { from: 'admin', to: 'user' } },
    { id: 11, action: 'user.email_changed', created_at: '2026-07-01T10:00:00Z', target_user_id: 42, actor_user_id: 1, actor_email: 'admin@example.test', actor_telegram_id: null, details: { from: 'before@example.test', to: 'alex@example.test' } },
  ];
  return async (url: URL, init?: RequestInit) => {
    if (!url.pathname.startsWith('/api/admin/')) return null;
    const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
    if (url.pathname === '/api/admin/me') {
      if (query.get('state') === 'admin-denied') return json({ detail: 'Нет доступа' }, 403);
      if (query.get('state') === 'admin-loading') return new Promise<Response>(() => {});
      return json({ id: 1, role: query.get('role') === 'admin' ? 'admin' : 'superadmin', email: 'admin@example.test', telegram_id: null, can_manage_own_premium: false });
    }
    if (url.pathname === '/api/admin/users/42/email' && init?.method === 'PATCH') {
      if (saveFailures-- > 0) return json({ detail: 'Email не сохранён. Повторите попытку.' }, 503);
      const draft = JSON.parse(String(init.body)).email;
      if (typeof draft !== 'string' || !draft.includes('@')) return json({ detail: 'Проверьте email' }, 400);
      email = draft;
      return json({ ok: true });
    }
    if (url.pathname === '/api/admin/tools/notifications/preview' && init?.method === 'POST') {
      return json({ id: 'fixture-only', count: 3, devices: 2, sample: [{ id: 42, display_name: 'Александр' }], push_enabled: true });
    }
    if (url.pathname === '/api/admin/tools/prediction-recovery/preview' && init?.method === 'POST') {
      const { season, round } = JSON.parse(String(init.body));
      return json({ id: 'fixture-check', season, round, state: 'ready', additions: { safety_car: 1 }, missing: [], conflict: false,
        changes: [{ user_id: 42, old_points: 8, new_points: 10, old_max: 26, new_max: 28, delta: 2 }] });
    }
    if (init?.method && init.method !== 'GET') return json({ detail: 'В предпросмотре изменения отключены' }, 403);
    if (url.pathname === '/api/admin/tools/control') {
      if (failures-- > 0) return json({ detail: 'Не удалось загрузить сводку. Повторите запрос.' }, 503);
      return json({ as_of: 1793520000, counts: { failed: 2, retry: 4, blocked: 1, unknown: 0, pending: 8 }, oldest_pending: 1793519900, recoveries: {}, push_configured: true, incomplete: empty ? [] : [stage], operations: { worker_healthy: true, disk_free_bytes: 32 * 1024 ** 3, forecasts: { pending: 0, oldest: null }, backups: { last_verified: 1793516400, pending_replication: 0, last_replicated: 1793517000 }, jobs: [{ name: 'notification_dispatch', last_success: 1793519990, overdue: false, error: null }] } });
    }
    if (url.pathname.endsWith('/deliveries')) {
      const deliveries = [
        { event_key: 'race:2026:19:prediction_results', recipient: 12345, channel: 'telegram', status: 'failed', attempts: 3, next_attempt: 0, updated: 1793519700, message_id: null, error: 'request_timeout', expires: 1793606400 },
        { event_key: 'race:2026:19:prediction_results', recipient: 80, channel: 'webpush', status: 'retry', attempts: 1, next_attempt: 1793521300, updated: 1793519600, message_id: null, error: 'temporary_unavailable', expires: 1793606400 },
      ];
      const status = url.searchParams.get('status');
      const channel = url.searchParams.get('channel');
      return json({ items: empty ? [] : deliveries.filter(item => (!channel || channel === 'all' || channel === item.channel) && (!status || ['all', 'attention', item.status].includes(status))), has_more: false });
    }
    if (url.pathname === '/api/admin/users') {
      const user = { id: 42, email, telegram_id: 12345, telegram_username: 'demo_driver', display_name: 'Александр', created_at: '2026-09-20T10:00:00Z', last_activity: '2026-11-01T10:00:00Z', role: 'user', email_verified: true, protected: false };
      const items = query.get('state') === 'admin-empty' || (url.searchParams.get('search') && !JSON.stringify(user).toLowerCase().includes(url.searchParams.get('search')!.toLowerCase())) || (url.searchParams.has('role') && url.searchParams.get('role') !== 'all' && url.searchParams.get('role') !== 'user') ? [] : [user];
      return json({ items, page: 1, pages: 1, total: items.length, page_size: 25 });
    }
    if (url.pathname === '/api/admin/audit-log') {
      const params = url.searchParams;
      const rows = empty ? [] : history.filter(item => {
        const day = item.created_at.slice(0, 10);
        const actor = params.get('actor')?.trim().toLowerCase();
        return (!params.has('before') || item.id < Number(params.get('before')))
          && (!params.has('date_from') || day >= params.get('date_from')!)
          && (!params.has('date_to') || day <= params.get('date_to')!)
          && (!params.has('target_user_id') || item.target_user_id === Number(params.get('target_user_id')))
          && (!params.has('action') || item.action === params.get('action'))
          && (!actor || item.actor_email.includes(actor) || String(item.actor_user_id) === actor);
      });
      const limit = Number(params.get('limit') ?? 50);
      const items = rows.slice(0, limit);
      return json({ items, next_before: rows.length > limit ? items.at(-1)?.id : null });
    }
    if (url.pathname === '/api/admin/game-records') return json({ games: [{ key: 'reaction', label: 'Игра на реакцию', records: 24, players: 8 }, { key: 'race', label: 'Emerald Loop', records: 12, players: 5 }, { key: 'reflex', label: 'Reflex Grid', records: 7, players: 3 }], total_records: 43, total_players: 12 });
    if (url.pathname.endsWith('/prediction-recovery/rounds')) return json({ rounds: empty || Number(url.searchParams.get('season')) !== 2026 ? [] : [
      { ...stage, current: { fastest_lap_driver: 'NOR', safety_car: null }, first_retirement_drivers: ['HAM'] },
      { ...stage, round: 20, event_name: 'Гран-при Мехико', missing: [], current: { safety_car: 0 }, first_retirement_drivers: ['HAM'] },
    ] });
    if (url.pathname.endsWith('/prediction-recovery')) return json([]);
    if (url.pathname.endsWith('/prediction-results/preview')) return json({ ...stage, fingerprint: 'demo', body: 'Демонстрационные итоги этапа', provisional: true, participants: 10, recipients: { telegram: 6, web: 4 }, already_sent: false });
    if (url.pathname.endsWith('/recap-news')) {
      const articles = [
        { ...stage, id: 1, source_id: 'openf1-control', title: 'Дирекция обновила итоговую классификацию', published: 1793519800, hidden: false },
        { ...stage, id: 2, source_id: 'openf1-control', title: 'Повторная публикация протокола', published: 1793519800, hidden: true },
      ];
      const visibility = url.searchParams.get('visibility');
      const selectedRound = Number(url.searchParams.get('round_num')) || (url.searchParams.get('latest') === 'true' ? stage.round : null);
      return json({ selected_round: selectedRound, stages: empty ? [] : [stage],
        sources: [{ id: 'openf1-control', publisher: 'OpenF1', terms_url: 'https://openf1.org/', enabled: true, permission_note: 'Журнал дирекции гонки', checked: 1793519800, successful: 1793519000, next_check: 1793521300, error: 'Временный сбой источника' }],
        items: empty || Number(url.searchParams.get('season')) !== 2026 ? [] : articles.filter(article => (!selectedRound || selectedRound === article.round) && (visibility !== 'visible' || !article.hidden) && (visibility !== 'hidden' || article.hidden)),
      });
    }
    if (url.pathname.endsWith('/product-analytics')) {
      if (reportFailures-- > 0) return json({ detail: 'Отчёт временно недоступен' }, 503);
      const empty = query.get('state') === 'admin-empty';
      const end = 1795222800;
      const interval = Number(url.searchParams.get('days') ?? 30) * 86400;
      return json({
        period: { start: end - interval, end },
        traffic: { start: end - interval, end, previous_start: end - 2 * interval,
          first_visit: empty ? null : end - 200 * 86400, current: empty ? { browsers: 0, returning: 0 } : { browsers: 1840, returning: 460 },
          previous: empty ? null : { browsers: 1600, returning: 352 } },
        funnel: empty ? { opened: 0, started: 0, saved: 0 } : { opened: 260, started: 192, saved: 143 },
        first_saves: empty ? 0 : 171,
        prediction_first: empty ? null : end - 40 * 86400, interaction_first: empty ? null : end - 70 * 86400,
        screens: empty ? [] : [{ path: '/predictions', views: 960, browsers: 610 }, { path: '/season', views: 721, browsers: 492 }],
        actions: empty ? [] : [{ path: '/predictions', action: 'prediction_submit', destination: '', clicks: 185, browsers: 133 }],
        retention: empty ? [] : [{ season: 2026, round: 18, next_round: 19, participants: 102, returned: 76 }],
        errors: [], quality: [],
      });
    }
    if (url.pathname.endsWith('/insights')) return json({ accounts: { total: 48, new_users: 4 }, visitors: { unique_browsers: 36, returning_browsers: 12 }, inbox: { total: 20, read_count: 14 }, queue: { pending: 0, exhausted: 0 }, reach: { members: 25, push_users: 8 } });
    if (url.pathname.endsWith('/notifications')) return json({ items: empty ? [] : [
      { id: 'sample', actor_id: 1, title: 'Итоги этапа готовы', body: 'Открыт разбор результатов прогнозов.', url: '/predictions', created_at: 1793520000, sent_at: 1793520060, audience: 28, recipients: 27, queued: 12, read_count: 9 },
    ] });
    return json({});
  };
}
