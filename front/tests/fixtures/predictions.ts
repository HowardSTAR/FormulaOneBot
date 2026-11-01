// Fictional, local-only responses for the real predictions screen. Never imported by production.
export function predictionPreview(query: URLSearchParams, drivers: {code: string; name: string; constructorName: string; imageUrl?: string}[]) {
  const scenario = query.get('state');
  const dense = scenario === 'production-layout';
  const guest = !['member', 'linked'].includes(query.get('auth') || '');
  const fields = [
    ['pole_driver', 'Поул-позиция', 3, [0,0,0]], ['winner_driver', 'Победитель', 8, [3,2,1]],
    ['second_driver', '2 место', 5, [2,1,0]], ['third_driver', '3 место', 4, [2,1,0]],
    ['fourth_driver', '4 место', 3, [1,0,0]], ['fifth_driver', '5 место', 2, [1,0,0]],
    ['fastest_lap_driver', 'Лучший круг', 3, [0,0,0]], ['first_retirement_driver', 'Первый сход', 5, [0,0,0]],
    ['safety_car', 'Машина безопасности', 4, [0,0,0]],
  ].map(([key,label,exact,offsets]) => ({key,label,exact,offsets}));
  const round = {season: 2026, round: 20, event_name: 'Гран-при Мексики', short_code: 'MEX', max_points: 37};
  let profile = {completed: scenario !== 'prediction-name', display_name: guest ? 'Гостевой черновик' : 'Alex Racing'};
  let saved = scenario === 'prediction-saved' || query.get('saved') === '1' ? {pole_driver: 'LEC', winner_driver: 'NOR', second_driver: 'PIA', third_driver: 'VER', fourth_driver: 'LEC', fifth_driver: 'HAM', fastest_lap_driver: 'NOR', first_retirement_driver: 'STR', safety_car: true, championship: { drivers: { id: 'norris', yes: true }, constructors: { id: 'mercedes', yes: false } }} : null;
  let loadFailures = scenario === 'prediction-error' ? 2 : 0;
  let saveFailures = scenario === 'prediction-save-error' ? 1 : 0;
  let leagues = scenario === 'prediction-empty' ? [] : [{id: 1, name: 'Друзья паддока', owner: false, invite_token: null, mode: 'season', season: 2026, rounds: []}];
  const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
  return async (url: URL, init?: RequestInit): Promise<Response | null> => {
    const method = init?.method || 'GET';
    if (!url.pathname.startsWith('/api/predictions/')) return null;
    if (['/api/predictions/preview', '/api/predictions/current'].includes(url.pathname)) {
      if (method === 'POST') {
        if (saveFailures-- > 0) return json({detail: 'Демо: не удалось сохранить прогноз. Попробуйте ещё раз.'}, 503);
        saved = JSON.parse(String(init?.body)); return json({ok: true});
      }
      if (loadFailures-- > 0) return json({detail: 'Демо: данные этапа временно недоступны.'}, 503);
      if (scenario === 'prediction-loading') return new Promise(() => {});
      return json({...round, status: scenario === 'prediction-finished' ? 'season_finished' : 'ok', round: scenario === 'prediction-finished' ? null : round.round,
        opens_at_utc: new Date(Date.now() + (scenario === 'prediction-before' ? 86400000 : -86400000)).toISOString(),
        deadline_utc: new Date(Date.now() + (scenario === 'prediction-closed' ? -3600000 : 86400000)).toISOString(),
        is_open: !['prediction-before', 'prediction-closed', 'prediction-finished'].includes(scenario || ''), has_sprint: query.get('format') === 'sprint', profile, drivers, prediction: saved,
        scoring_rules: query.get('format') === 'sprint' ? [{key: 'sprint_pole_driver', label: 'Спринт-поул', exact: 3, offsets: [0,0,0]}, {key: 'sprint_winner_driver', label: 'Спринт-победа', exact: 3, offsets: [0,0,0]}, ...fields] : fields});
    }
    if (url.pathname.endsWith('/profile')) { profile = {...profile, ...JSON.parse(String(init?.body)), completed: true}; return json(profile); }
    if (url.pathname.endsWith('/championship')) {
      const mode = query.get('championship');
      if (!['1', 'both', 'multiple'].includes(mode || '')) return json({status: 'not_applicable', drivers: [], constructors: []});
      const driver = {id: 'norris', name: 'Ландо Норрис', points: 390, remaining_points: 25, has_sprint: false, wins: 8, future_races: 1,
        scenarios: [{points: 25, rivals: [{id: 'piastri', name: 'Оскар Пиастри', points: 355, max_points: 9, tie_points: null}], finishes: [{race: [1], sprint: []}]}]};
      const team = {id: 'mercedes', name: 'Mercedes', points: 607, remaining_points: 43, has_sprint: false, wins: 9, future_races: 1,
        scenarios: [{points: 43, rivals: [{id: 'ferrari', name: 'Ferrari', points: 530, max_points: 8, tie_points: null}], finishes: [{race: [1,2], sprint: []}]}]};
      return json({status: 'ok', drivers: mode === 'multiple' ? [driver, {...driver, id: 'piastri', name: 'Оскар Пиастри', points: 355}] : [driver],
        constructors: mode === 'both' ? [team] : [], scope: 'К концу этапа', note: 'Демонстрационные условия, не актуальный расчёт чемпионата.'});
    }
    const entries = scenario === 'prediction-empty' ? [] : ['Alex Racing', 'Позднее торможение', 'Болельщик с очень длинным именем'].map((display_name, index) => ({user_id: index + 1, place: index + 1, display_name, total_points: 126 - index * 8, rounds_scored: 7, wins: 2 - Math.min(2,index), best_points: 27, average_points: 18 - index, history: [{...round, points: 22-index*3}]}));
    const seasonRounds = dense ? ['Гран-при Венгрии', 'Гран-при Италии', 'Гран-при Азербайджана', 'Гран-при Сингапура', 'Гран-при США', 'Гран-при Мексики', 'Гран-при Бразилии'].map((event_name, index) => ({...round, round: index + 14, event_name, short_code: ['HUN','ITA','AZE','SGP','USA','MEX','BRA'][index]})) : [round];
    const seasonEntries = dense ? Array.from({length: 36}, (_, index) => {
      const history = seasonRounds.map((r, n) => ({...r, points: Math.max(0, 25 - index + n % 3)}));
      return { ...entries[index % entries.length], user_id: index + 1, place: index + 1, display_name: index < 3 ? entries[index].display_name : `Участник ${index + 1}`, total_points: history.reduce((sum, r) => sum + r.points, 0), history };
    }) : entries;
    if (url.pathname.endsWith('/leaderboard')) return json({season: 2026, entries: seasonEntries, rounds: seasonRounds, current_user_id: 1});
    if (url.pathname.endsWith('/personal-season')) return json({season: 2026, history: scenario === 'prediction-empty' ? [] : dense ? seasonRounds.map((r, n) => ({...r, points: [8,12,15,20,5,11,25][n]})) : [{...round, points: 25}], latest: scenario === 'prediction-empty' ? null : {...(dense ? seasonRounds.at(-1)! : round), points: 25, items: [{label: 'Победитель', status: 'exact'}, {label: '4 место', status: 'exact'}, {label: '5 место', status: 'exact'}, {label: 'Лучший круг', status: 'exact'}, {label: 'Первый сход', status: 'exact'}]}, previous_points: dense ? 11 : null, best_points: 25, average_points: dense ? 13.7 : 25, place: dense ? 2 : 1, place_change: 1, gap_to_higher: dense ? 14 : null, achievements: ['Первый сохранённый прогноз'], categories: [{label: 'Победитель', exact: 3, known: 7}]});
    if (url.pathname.includes('/mine/')) {
      const outcomes: Record<string, {predicted: string | number; actual: string | number | string[]; status: string; points: number; position: number | null}> = {
        pole_driver: {predicted: 'NOR', actual: 'LEC', status: 'miss', points: 0, position: null},
        winner_driver: {predicted: 'NOR', actual: 'NOR', status: 'exact', points: 8, position: 1},
        second_driver: {predicted: 'PIA', actual: 'VER', status: 'partial', points: 2, position: 3},
        third_driver: {predicted: 'VER', actual: 'PIA', status: 'partial', points: 2, position: 2},
        fourth_driver: {predicted: 'LEC', actual: 'LEC', status: 'exact', points: 3, position: 4},
        fifth_driver: {predicted: 'HAM', actual: 'HAM', status: 'exact', points: 2, position: 5},
        fastest_lap_driver: {predicted: 'NOR', actual: 'NOR', status: 'exact', points: 3, position: null},
        first_retirement_driver: {predicted: 'STR', actual: ['STR','ALO'], status: 'exact', points: 5, position: null},
        safety_car: {predicted: 1, actual: 0, status: 'miss', points: 0, position: null},
      };
      const items = fields.map(field => ({...field, rule: field, ...outcomes[String(field.key)], maximum: field.exact,
        reason: outcomes[String(field.key)].status === 'exact' ? 'Точное попадание. Демонстрационный результат.' : outcomes[String(field.key)].status === 'partial' ? 'Пилот финишировал рядом с выбранным местом. Начислены частичные баллы.' : 'Результат не совпал с прогнозом.'}));
      const selectedRound = seasonRounds.find(r => r.round === Number(url.pathname.split('/').at(-1))) || round;
      return json({...selectedRound, points: items.reduce((total,item) => total + item.points,0), complete: true, items, race_facts: {source: 'Демо', safety_car: 0, first_retirement_drivers: ['STR','ALO'], retirement_order_confirmed: true}});
    }
    if (url.pathname.endsWith('/leagues') && method === 'POST') { leagues = [...leagues, {id: 2, name: JSON.parse(String(init?.body)).name, mode: 'season', season: 2026, owner: false, invite_token: null, rounds: []}]; return json({id: 2}); }
    if (url.pathname.endsWith('/leagues')) return json({leagues});
    if (url.pathname.includes('/leagues/')) return json({season: 2026, mode: 'season', entries, rounds: [round]});
    return json({});
  };
}
