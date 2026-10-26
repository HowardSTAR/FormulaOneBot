// Deterministic fictional history for visual checks. Never imported by production routes.
export function historyPreview(query: URLSearchParams, drivers: { driverId: string; name: string; constructorName: string }[], teams: { constructorId: string; name: string }[]) {
  const state = query.get('state');
  let failures = state === 'history-error' ? 1 : 0;
  let rosterFailures = state === 'history-roster-error' ? 1 : 0;
  const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
  return (url: URL): Response | Promise<Response> | null => {
    if (['/api/drivers', '/api/constructors'].includes(url.pathname)) {
      if (rosterFailures-- > 0) return json({ detail: 'Демонстрация ошибки состава' }, 503);
      if (state === 'history-roster-empty') return json({ drivers: [], constructors: [] });
      if (state === 'history-roster-loading') return new Promise<Response>(() => {});
      return null;
    }
    if (url.pathname !== '/api/standings-history') return null;
    if (failures-- > 0) return json({ detail: 'История временно недоступна. Повторите поиск.' }, 503);
    if (state === 'history-loading') return new Promise<Response>(() => {});
    const start = Number(url.searchParams.get('start_year'));
    const end = Number(url.searchParams.get('end_year'));
    const kind = url.searchParams.get('kind');
    const selected = (url.searchParams.get('ids') || '').split(',').filter(Boolean);
    const years = Array.from({ length: end - start + 1 }, (_, index) => ({ season: start + index, status: state === 'history-empty' || state === 'history-partial' && index === 2 ? 'unavailable' : 'available', source: `https://api.jolpi.ca/ergast/f1/${start + index}/${kind === 'constructors' ? 'constructorStandings' : 'driverStandings'}.json` }));
    const series = selected.map((id, index) => {
      const driver = drivers.find(row => row.driverId === id);
      const team = teams.find(row => row.constructorId === id);
      const name = kind === 'constructors' ? team?.name || id : driver?.name || id;
      return { id, name, seasons: years.map((year, yearIndex) => ({ ...year, current: year.season === 2026,
        standing: year.status !== 'available' || state === 'history-partial' && index === 1 && yearIndex === 1 ? null : {
          id, name, position: 1 + ((index * 3 + yearIndex * (index + 1)) % 10), points: 140 + index * 38 + yearIndex * 14.5,
          wins: (index + yearIndex) % 7, round: year.season === 2026 ? 19 : 22, teams: kind === 'constructors' ? [] : [driver?.constructorName || 'Команда демо'],
        },
      })) };
    });
    return json({ series, years, updated_at: '2026-10-26T12:00:00Z', note: 'Демонстрационные значения для проверки интерфейса. Системы начисления очков менялись; очки разных эпох напрямую несопоставимы. Текущий сезон — промежуточный. Разные ID команд не объединяются автоматически.' });
  };
}
