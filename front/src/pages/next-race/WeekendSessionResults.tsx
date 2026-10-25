import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { SessionItem } from '../../context/HeroDataContext';
import { CustomSelect } from '../../components/CustomSelect';
import { apiRequest } from '../../helpers/api';
import { resultStatus } from '../../helpers/presentation';
import { matchesWeekendResult, sessionStart, weekendSession, weekendSessionLink } from './weekend-model';
import './weekend-results.css';

type ResultRow = {
  position: number; name?: string; driver?: string; code?: string; team?: string;
  best?: string; time?: string | null; gap?: string | null; status?: string | null;
  laps?: number; points?: number; segment?: string; is_favorite_driver?: boolean;
};
type Response = { season?: number; round?: number | null; session?: number; results?: ResultRow[] };
type State = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; rows: ResultRow[] };

export function WeekendSessionResults({ season, round, eventName, sessions, selected, now }: {
  season: number; round: number; eventName: string; sessions: SessionItem[]; selected: string; now: number;
}) {
  const navigate = useNavigate();
  const title = useRef<HTMLHeadingElement>(null);
  const session = sessions.find(item => weekendSession(item.name)?.id === selected);
  const target = session && weekendSession(session.name);
  const started = session && (sessionStart(session) ?? Infinity) <= now;
  const [state, setState] = useState<State>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const path = target?.path;
  const practice = target?.practice;
  const summaryLink = weekendSessionLink(season, round);
  const fullQuery = new URLSearchParams({ mode: 'archive', season: String(season), round: String(round) });
  if (practice) fullQuery.set('session', String(practice));

  useEffect(() => { title.current?.focus(); }, []);
  useEffect(() => {
    if (!path || !started) return;
    let active = true;
    apiRequest<Response>(`/api${path}`, { season, round, ...(practice ? { session: practice } : {}) })
      .then(response => {
        if (!active) return;
        setState({ status: 'ready', rows: matchesWeekendResult(response, season, round, practice) ? response.results || [] : [] });
      })
      .catch(error => { if (active) setState({ status: 'error', message: error instanceof Error ? error.message : 'Не удалось загрузить результаты.' }); });
    return () => { active = false; };
  }, [path, practice, started, season, round, attempt]);

  const options = sessions.flatMap(item => {
    const target = weekendSession(item.name);
    if (!target) return [];
    return [{ value: target.id, label: item.name, disabled: (sessionStart(item) ?? Infinity) > now }];
  });
  const rows = state.status === 'ready' ? state.rows : [];
  const hasGap = rows.some(row => Boolean(row.gap));
  const hasLaps = rows.some(row => row.laps !== undefined);
  const hasPoints = rows.some(row => row.points !== undefined);

  return <main className="weekend-page weekend-session-page">
    <header className="weekend-session-header">
      <Link className="weekend-secondary" to={summaryLink}><span aria-hidden="true">←</span> К уик-энду</Link>
      <div className="weekend-session-select"><CustomSelect ariaLabel="Сессия уик-энда" options={options} value={selected}
        onChange={value => { const item = sessions.find(item => weekendSession(item.name)?.id === value); if (item) navigate(weekendSessionLink(season, round, item.name)); }} /></div>
    </header>
    <div className="weekend-session-title"><h1 ref={title} tabIndex={-1}>{session ? 'Результаты' : 'Сессия не найдена'}</h1><p>{eventName} · {season} · этап {round}</p></div>
    {!target || !started ? <p className="weekend-empty" role="status">Результаты этой сессии пока недоступны. Выберите прошедшую сессию или вернитесь к расписанию.</p>
      : state.status === 'loading' ? <div className="weekend-result-loading" role="status">Загружаем классификацию…<div aria-hidden="true"><span /><span /><span /></div></div>
      : state.status === 'error' ? <div className="weekend-result-feedback" role="alert"><p>{state.message}</p><button type="button" className="weekend-button" onClick={() => { setState({ status: 'loading' }); setAttempt(value => value + 1); }}>Повторить загрузку</button></div>
      : !state.rows.length ? <p className="weekend-empty" role="status">Классификация выбранной сессии ещё не опубликована. Источник может обновить её с задержкой после финиша.</p>
      : <ol className="weekend-classification" aria-label={`Классификация: ${session.name}`}>
        {state.rows.map((row, index) => {
          const code = row.driver || row.code;
          const name = row.name || code || 'Пилот не указан';
          const metrics = [
            { label: row.best ? 'Лучший круг' : 'Время / статус', value: row.best || row.time || resultStatus(row.status) },
            ...(hasGap ? [{ label: 'От лидера', value: row.gap || '—' }] : []),
            ...(hasLaps ? [{ label: 'Круги', value: row.laps ?? '—' }] : []),
            ...(hasPoints ? [{ label: 'Очки', value: row.points ?? '—' }] : []),
          ];
          return <li key={`${code || name}:${index}`}>
            <span className="weekend-result-position" aria-label={`Позиция ${row.position}`}>{String(row.position).padStart(2, '0')}</span>
            <div className="weekend-result-identity"><h2>{code ? <Link to={`/driver-details?code=${encodeURIComponent(code)}&season=${season}`}>{name}</Link> : name}{row.is_favorite_driver && <span className="weekend-result-favorite" aria-label="Избранный пилот">★</span>}</h2><p>{row.team || code || '—'}{row.segment && <span className="weekend-result-segment">{row.segment}</span>}</p></div>
            <dl className="weekend-result-metrics">{metrics.map(metric => <div key={metric.label}><dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}</dl>
          </li>;
        })}
      </ol>}
    {target && <Link className="weekend-secondary weekend-full-results" to={`${target.path}?${fullQuery}`}>Полная страница результатов <span aria-hidden="true">↗</span></Link>}
  </main>;
}
