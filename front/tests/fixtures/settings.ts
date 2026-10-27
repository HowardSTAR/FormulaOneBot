// Local settings preview only. Reads and saves stay in memory; no backend writes.
export function settingsPreview(query: URLSearchParams) {
  const state = query.get('state');
  let loadFailures = state === 'settings-error' ? 1 : 0;
  let saveFailures = state === 'settings-save-error' ? 1 : 0;
  let settings = { timezone: 'Etc/GMT-3', notify_before: 60,
    notify_before_minutes: state === 'settings-empty' ? [] : [60],
    notifications_enabled: state !== 'settings-empty',
    reminder_sessions: state === 'settings-empty' ? 0 : 31, results_spoiler: false };
  return async (url: URL, init?: RequestInit): Promise<Response | null> => {
    if (url.pathname !== '/api/account/settings') return null;
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
      status, headers: { 'Content-Type': 'application/json' },
    });
    if (init?.method === 'POST') {
      if (state === 'settings-saving') await new Promise(resolve => setTimeout(resolve, 1500));
      if (saveFailures-- > 0) return json({ detail: 'Не удалось сохранить настройки. Попробуйте ещё раз.' }, 503);
      settings = { ...settings, ...JSON.parse(String(init.body)) };
      return json({ status: 'ok' });
    }
    if (state === 'settings-loading') return new Promise<Response>(() => {});
    if (loadFailures-- > 0) return json({}, 503);
    return json(settings);
  };
}
