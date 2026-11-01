// Isolated design preview. No admin request or mutation reaches the backend.
export function adminPreview(query: URLSearchParams) {
  let failures = query.get('state') === 'admin-error' ? 1 : 0;
  let saveFailures = query.get('state') === 'admin-save-error' ? 1 : 0;
  let email = 'alex@example.test';
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
    if (init?.method && init.method !== 'GET') return json({ detail: 'В предпросмотре изменения отключены' }, 403);
    if (url.pathname === '/api/admin/tools/control') {
      if (failures-- > 0) return json({ detail: 'Не удалось загрузить сводку. Повторите запрос.' }, 503);
      return json({ as_of: 1793520000, counts: { failed: 2, retry: 4, blocked: 1, unknown: 0, pending: 8 }, oldest_pending: 1793519900, recoveries: {}, push_configured: true, incomplete: [], operations: { worker_healthy: true, disk_free_bytes: 32 * 1024 ** 3, forecasts: { pending: 0, oldest: null }, backups: { last_verified: 1793516400, pending_replication: 0, last_replicated: 1793517000 }, jobs: [{ name: 'notification_dispatch', last_success: 1793519990, overdue: false, error: null }] } });
    }
    if (url.pathname.endsWith('/deliveries')) return json({ items: query.get('state') === 'admin-empty' ? [] : [{ event_key: 'race:2026:19:prediction_results', recipient: 12345, channel: 'telegram', status: url.searchParams.get('status') === 'all' ? 'failed' : url.searchParams.get('status') || 'failed', attempts: 3, next_attempt: 0, updated: 1793519700, message_id: null, error: 'request_timeout', expires: 1793606400 }], has_more: false });
    if (url.pathname === '/api/admin/users') {
      const user = { id: 42, email, telegram_id: 12345, telegram_username: 'demo_driver', display_name: 'Александр', created_at: '2026-09-20T10:00:00Z', last_activity: '2026-11-01T10:00:00Z', role: 'user', email_verified: true, protected: false };
      const items = query.get('state') === 'admin-empty' || (url.searchParams.get('search') && !JSON.stringify(user).toLowerCase().includes(url.searchParams.get('search')!.toLowerCase())) || (url.searchParams.get('role') !== 'all' && url.searchParams.get('role') !== 'user') ? [] : [user];
      return json({ items, page: 1, pages: 1, total: items.length, page_size: 25 });
    }
    if (url.pathname === '/api/admin/audit-log') return json({ items: query.get('state') === 'admin-empty' ? [] : [{ id: 1, action: 'user.role_changed', created_at: '2026-11-01T09:00:00Z', target_user_id: 42, actor_email: 'admin@example.test', actor_telegram_id: null, details: { from: 'admin', to: 'user' } }] });
    if (url.pathname === '/api/admin/game-records') return json({ games: [{ key: 'reaction', label: 'Игра на реакцию', records: 24, players: 8 }, { key: 'race', label: 'Emerald Loop', records: 12, players: 5 }, { key: 'reflex', label: 'Reflex Grid', records: 7, players: 3 }], total_records: 43, total_players: 12 });
    if (url.pathname.endsWith('/prediction-recovery/rounds')) return json({ rounds: [] });
    if (url.pathname.endsWith('/prediction-recovery')) return json([]);
    if (url.pathname.endsWith('/recap-news')) return json({ sources: [], items: [] });
    if (url.pathname.endsWith('/product-analytics')) return json({ funnel: { opened: 21, started: 15, saved: 12 }, interaction_first: null, screens: [], actions: [], retention: [], errors: [], quality: [] });
    if (url.pathname.endsWith('/insights')) return json({ accounts: { total: 48, new_users: 4 }, visitors: { unique_browsers: 36, returning_browsers: 12 }, inbox: { total: 20, read_count: 14 }, queue: { pending: 0, exhausted: 0 }, reach: { members: 25, push_users: 8 } });
    if (url.pathname.endsWith('/notifications')) return json({ items: [], history: [] });
    return json({});
  };
}
