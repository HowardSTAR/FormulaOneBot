// Isolated preview: mutations stay in memory, no delivery or backend calls.
export function notificationsPreview(query: URLSearchParams) {
  const scenario = query.get('state');
  let loadFailures = scenario === 'notifications-error' ? 1 : 0;
  let readFailures = scenario === 'notifications-read-error' ? 1 : 0;
  let moreFailures = scenario === 'notifications-more-error' ? 1 : 0;
  let read = false;
  const items = [
    { id: 6, title: 'Гран-при США: результаты гонки', body: 'Ландо Норрис выигрывает гонку в Остине.\nОскар Пиастри — второй, Макс Ферстаппен — третий.\nОткройте полную классификацию и очки пилотов.', url: '/race-results?season=2026&round=19', created_at: 1792962000, read_at: null, historical_snapshot: true, category: 'results' },
    { id: 5, title: 'Открыты прогнозы на Гран-при Мексики', body: 'Выберите свою тройку на ближайшую гонку. Прогноз можно изменить до начала квалификации.', url: '/predictions?season=2026&round=20', created_at: 1792922400, read_at: null, category: 'predictions' },
    { id: 4, title: 'Скоро квалификация', body: 'Гран-при Мексики\nКвалификация начнётся по расписанию. Проверьте время сессий перед стартом.', url: '/next-race?season=2026&round=20', created_at: 1792918800, read_at: 1792920000, reminder: { kind: 'quali', start_utc: '2026-10-31T21:00:00Z', duration_minutes: 60 }, category: 'reminders' },
    { id: 3, title: 'Как вам последний этап?', body: 'Оцените гонку и выберите пилота дня.\n' + 'В Остине борьба продолжалась до последних кругов. Поделитесь впечатлениями от этапа и посмотрите, как проголосовали другие болельщики. '.repeat(5), url: '/voting?season=2026&round=19', created_at: 1792886400, read_at: 1792920000, category: 'voting' },
    { id: 2, title: 'История событий доступна на сайте', body: 'Уведомления сохраняются в вашем аккаунте. Push можно включить отдельно на каждом устройстве.', url: '/settings', created_at: 1792800000, read_at: 1792920000, category: 'admin', priority: 'low' },
  ];
  return async (url: URL): Promise<Response | null> => {
    if (!url.pathname.startsWith('/api/web-notifications')) return null;
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
    if (url.pathname.endsWith('/unread-count')) return json({ unread: read ? 0 : 2 });
    if (url.pathname.endsWith('/read')) {
      if (scenario === 'notifications-reading') await new Promise(resolve => setTimeout(resolve, 1500));
      if (readFailures-- > 0) return json({}, 503);
      read = true; return json({ ok: true });
    }
    if (url.pathname.endsWith('/subscription')) return scenario === 'notifications-push-error' ? json({ detail: 'Не удалось сохранить подписку. Попробуйте ещё раз.' }, 503) : json({ ok: true });
    if (url.pathname !== '/api/web-notifications') return json({}, 404);
    if (scenario === 'notifications-loading') return new Promise<Response>(() => {});
    if (loadFailures-- > 0) return json({ detail: 'История временно недоступна.' }, 503);
    const before = Number(url.searchParams.get('before'));
    if (before && moreFailures-- > 0) return json({}, 503);
    const category = url.searchParams.get('category') || 'all';
    let filtered = scenario === 'notifications-empty' ? [] : items.filter(item => category === 'all' || item.category === category);
    const unread = read ? 0 : filtered.filter(item => !item.read_at).length;
    if (before) filtered = [{ ...items[4], id: 1, title: 'Добро пожаловать в TurboTears' }];
    if (scenario === 'notifications-duplicates' && !before) filtered = [items[0], { ...items[0], id: 1 }];
    return json({ items: filtered.map(item => ({ ...item, read_at: read ? 1793000000 : item.read_at })), unread,
      next_before: !before && category === 'all' && filtered.length ? 2 : null,
      push: { enabled: scenario !== 'notifications-push-off', public_key: 'BA' },
    });
  };
}
