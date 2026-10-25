import { lazy, Suspense, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CustomSelect } from './CustomSelect';
import { SessionClassification } from './SessionClassification';
import { GlassSwitch } from '../pages/index/GlassSwitch';
import { apiRequest } from '../helpers/api';
import { useSessionFilters } from '../helpers/sessionFilters';
import type { SessionResultKind, SessionResultRow } from '../helpers/sessionClassification';
import '../pages/next-race/weekend.css';
import '../pages/next-race/weekend-results.css';

const SessionRaceRecap = lazy(() => import('./SessionRaceRecap'));

type Race = { round: number; event_name?: string; available_practice_sessions?: number[]; is_sprint_weekend?: boolean };
type Payload = { season: number; round: number | null; session?: number; data_incomplete?: boolean; available_sessions?: number[]; is_sprint_weekend?: boolean; race_info?: { event_name?: string }; results?: SessionResultRow[] };
const labels: Record<SessionResultKind,string> = { practice: 'Свободные заезды', quali: 'Квалификация', 'sprint-quali': 'Спринт-квалификация', sprint: 'Спринт', race: 'Гонка' };
const sessionTypes = { practice: 'practice', quali: 'quali', 'sprint-quali': 'sprint_quali', sprint: 'sprint', race: 'race' };

export function SessionResultsPage({ kind }: { kind: SessionResultKind }) {
  const minYear = kind === 'practice' ? 2018 : kind.startsWith('sprint') ? 2021 : 1950;
  const { season, mode, selectedRound, setSelectedRound, selectedSession } = useSessionFilters(minYear);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [attempt, setAttempt] = useState(0);
  const seasonKey = `${season}:${kind}:${attempt}`;
  const [schedule, setSchedule] = useState<{ key: string; races: Race[]; error?: string } | null>(null);
  const requestKey = `${seasonKey}:${mode}:${selectedRound}:${selectedSession}`;
  const [result, setResult] = useState<{ key: string; data?: Payload; error?: string } | null>(null);
  const archive = mode === 'archive';
  const scheduleLoading = schedule?.key !== seasonKey;
  const races = scheduleLoading ? [] : schedule?.races || [];
  const loading = (archive && scheduleLoading) || ((!archive || selectedRound !== null) && result?.key !== requestKey);
  const data = !loading && result?.key === requestKey ? result.data : undefined;
  const error = (archive && !scheduleLoading && schedule?.error) || (!loading && result?.key === requestKey && result.error);
  useEffect(() => {
    let active = true;
    apiRequest<{ races?: Race[] }>('/api/season', { season, completed_only: true, session_type: sessionTypes[kind] }).then(response => {
      if (!active) return;
      const races = (response.races || []).filter(race => race.round > 0).sort((a,b) => b.round - a.round);
      setSchedule({ key: seasonKey, races });
      // Preserve explicit direct links, including unpublished stages, rather than silently substituting another event.
      setSelectedRound(current => current ?? races[0]?.round ?? null);
    }).catch(() => { if (active) setSchedule({ key: seasonKey, races: [], error: 'Не удалось загрузить список этапов. Повторите загрузку.' }); });
    return () => { active = false; };
  }, [season, kind, seasonKey, setSelectedRound]);
  useEffect(() => {
    if (archive && selectedRound === null) return;
    let active = true;
    apiRequest<Payload>(`/api/${kind}-results`, { season, ...(archive ? { round: selectedRound } : {}), ...(kind === 'practice' ? { session: selectedSession } : {}) }).then(response => {
      if (!active) return;
      const matches = response.season === season && (!archive || response.round === selectedRound) && (kind !== 'practice' || response.session === selectedSession);
      setResult({ key: requestKey, data: matches ? response : { season, round: selectedRound, results: [] } });
    }).catch(reason => { if (active) setResult({ key: requestKey, error: reason instanceof Error ? reason.message : 'Не удалось загрузить результаты.' }); });
    return () => { active = false; };
  }, [archive, kind, season, selectedRound, selectedSession, requestKey]);
  const selectSeason = (value: string | number) => setParams(previous => {
    const next = new URLSearchParams(previous);
    next.set('season', String(value));
    next.set('mode', 'archive');
    next.delete('round');
    if (kind === 'practice') next.set('session', '1');
    return next;
  });
  const link = (nextKind: SessionResultKind, session?: number) => {
    const next = new URLSearchParams(params);
    if (session) next.set('session', String(session)); else next.delete('session');
    return `/${nextKind}-results?${next}`;
  };
  const selectedRace = races.find(race => race.round === (archive ? selectedRound : data?.round));
  const available = selectedRace?.available_practice_sessions || data?.available_sessions || (selectedRace?.is_sprint_weekend || data?.is_sprint_weekend ? [1] : [1,2,3]);
  const practiceSessions = available.filter(session => [1,2,3].includes(session));
  const sessionItems = kind === 'practice' ? practiceSessions.map(session => ({ id: String(session), label: `P${session}`, to: link('practice',session) }))
    : (kind.startsWith('sprint') ? ['sprint-quali','sprint'] as const : ['quali','race'] as const).map(value => ({ id: value, label: value === 'sprint-quali' ? 'Квалификация' : labels[value], to: link(value) }));
  const category = kind === 'practice' ? 'practice' : kind.startsWith('sprint') ? 'sprint' : 'weekend';
  const label = kind === 'practice' ? `Практика ${selectedSession}` : labels[kind];
  const round = data?.round ?? selectedRound;
  return <main className="weekend-page weekend-session-page">
    <header className="weekend-session-header">
      <Link className="weekend-secondary" to={`/season?year=${season}${round ? `&round=${round}` : ''}&filter=all`}><span aria-hidden="true">←</span> К календарю</Link>
      <div className="session-results-year"><span>Сезон</span><CustomSelect ariaLabel="Сезон результатов" value={season} onChange={selectSeason} options={Array.from({ length: new Date().getFullYear() - minYear + 1 }, (_,i) => ({ value: new Date().getFullYear() - i, label: String(new Date().getFullYear() - i) }))} /></div>
    </header>
    <div className="weekend-session-title"><h1>{labels[kind]}</h1><p>{data?.race_info?.event_name || selectedRace?.event_name || 'Результаты сессии'} · {season}{round ? ` · этап ${round}` : ''}</p></div>
    <div className="session-results-archive"><GlassSwitch className="weekend-result-switch" label="Период результатов" selected={mode} replace items={['latest','archive'].map(value => { const query = new URLSearchParams(params); query.set('mode',value); return { id: value, label: value === 'latest' ? 'Последние' : 'Архив', to: `/${kind}-results?${query}` }; })} />
    {archive && <div className="session-results-round"><CustomSelect ariaLabel="Этап" options={races.map(race => ({ value: race.round, label: `Этап ${race.round} · ${race.event_name || 'Grand Prix'}` }))} value={selectedRound ?? ''} onChange={value => { const race = races.find(race => race.round === Number(value)); const available = race?.available_practice_sessions || (race?.is_sprint_weekend ? [1] : [1,2,3]); setSelectedRound(Number(value), kind === 'practice' && !available.includes(selectedSession) ? 1 : undefined); }} /></div>}
    </div>
    <section className="weekend-result-controls" aria-label="Выбор результатов">
      <div className="weekend-session-select"><CustomSelect ariaLabel="Раздел результатов" value={category} options={[{ value: 'practice', label: 'Практика', disabled: season < 2018 },{ value: 'sprint', label: 'Спринт', disabled: season < 2021 },{ value: 'weekend', label: 'Уик-энд' }]} onChange={value => navigate(link(value === 'practice' ? 'practice' : value === 'sprint' ? 'sprint-quali' : 'quali', value === 'practice' ? 1 : undefined))} /></div>
      <GlassSwitch className={`weekend-result-switch${kind === 'practice' && !practiceSessions.includes(selectedSession) ? ' is-unavailable' : ''}`} label="Сессия" selected={kind === 'practice' ? String(selectedSession) : kind} replace items={sessionItems} />

      <p className="weekend-result-session-name">{label}</p>
    </section>
    {loading ? <div className="weekend-result-loading" role="status">Загружаем классификацию…<div aria-hidden="true"><span /><span /><span /></div></div>
      : error ? <div className="weekend-result-feedback" role="alert"><p>{error}</p><button type="button" className="weekend-button" onClick={() => setAttempt(value => value + 1)}>Повторить загрузку</button></div>
      : !data?.results?.length ? <p className="weekend-empty" role="status">{data?.data_incomplete ? 'Результаты обрабатываются. Данные появятся после обновления источника.' : 'Классификация выбранной сессии ещё не опубликована. Выберите другой этап или сессию.'}</p>
      : <SessionClassification rows={data.results} kind={kind} season={season} label={label} />}
    {kind === 'race' && !loading && !error && data?.round && !!data.results?.length && <Suspense fallback={<p role="status">Загружаем обзор гонки…</p>}><SessionRaceRecap season={season} round={data.round} rows={data.results} /></Suspense>}
  </main>;
}
