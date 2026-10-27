// Fictional state for the account design preview only. No backend mutations.
export function accountPreview(query: URLSearchParams) {
  let signedIn = ['member', 'linked'].includes(query.get('auth') || '');
  let linked = query.get('auth') === 'linked';
  const state = query.get('state');
  let accountFailures = state === 'account-error' ? 1 : 0;
  let boostyFailures = state === 'account-boosty-error' ? 1 : 0;
  let actionFailures = state === 'account-action-error' ? 1 : 0;
  const supporter = query.get('tier') === '3';
  const user = () => ({ id: 1, email: query.get('email') === 'none' ? null : query.get('email') || 'racer@example.com',
    telegram_id: linked ? 1 : null, role: 'user', email_verified: state !== 'account-unverified', display_name: 'Turbo Racer' });
  const boosty = { eligible: query.get('email') !== 'none', configured: true, active: supporter, premium_active: supporter, premium_override: null,
    can_check: true, blog_url: 'https://boosty.to/turbotears', level_name: supporter ? 'Полный газ' : null,
    checked_at: null, expires_at: null, check_failed: false, check_unavailable_reason: null };
  return async (url: URL, init?: RequestInit): Promise<Response | null> => {
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
    if (url.pathname === '/api/auth/me') {
      if (init?.signal && state === 'account-loading') return new Promise<Response>(() => {});
      if (init?.signal && accountFailures-- > 0) return json({ detail: 'Не удалось загрузить аккаунт. Попробуйте ещё раз.' }, 503);
      return signedIn ? json(user()) : json({}, 401);
    }
    if (url.pathname === '/api/account/boosty') {
      if (boostyFailures-- > 0) return json({}, 503);
      return json(boosty);
    }
    if (!url.pathname.startsWith('/api/auth/') && url.pathname !== '/api/account/boosty/check') return null;
    if (init?.method && init.method !== 'GET' && actionFailures-- > 0) return json({ detail: 'Демонстрация ошибки. Повторите действие.' }, 503);
    if (url.pathname === '/api/auth/login') {
      signedIn = true;
      return json({ user: user(), csrf_token: 'local-preview-only' });
    }
    if (url.pathname === '/api/auth/logout') { signedIn = false; return new Response(null, { status: 204 }); }
    if (url.pathname === '/api/auth/password/forgot') return json({ message: 'Демо: ссылка для восстановления отправлена. Письмо не создавалось.' });
    if (url.pathname === '/api/auth/password/change') return json({ message: 'Демо: пароль изменён. Реальные данные не менялись.' });
    if (url.pathname === '/api/account/boosty/check') return json({ ...boosty, checked_at: Math.floor(Date.now() / 1000) });
    if (url.pathname === '/api/auth/telegram/link-by-code') { linked = true; return json({ user: user() }); }
    if (url.pathname === '/api/auth/telegram/link-sessions' && init?.method === 'POST') return json({
      detail: 'QR и ссылка доступны с работающим ботом. В демо используйте любой шестизначный код.',
    }, 503);
    // Do not simulate destructive operations or create accounts from this preview.
    return json({ detail: 'Это действие недоступно в демо.' }, 405);
  };
}
