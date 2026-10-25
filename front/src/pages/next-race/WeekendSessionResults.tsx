import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import type { SessionItem } from '../../context/HeroDataContext';
import { GlassSwitch } from '../index/GlassSwitch';
import { CustomSelect } from '../../components/CustomSelect';
import { apiRequest } from '../../helpers/api';
import { SessionClassification } from '../../components/SessionClassification';
import type { SessionResultKind, SessionResultRow } from '../../helpers/sessionClassification';
import { matchesWeekendResult, sessionStart, weekendSession, weekendSessionLink, weekendResultGroups } from './weekend-model';
import './weekend-results.css';

type Response = { season?: number; round?: number | null; session?: number; results?: SessionResultRow[] };
type State = { key: string; status: 'error'; message: string } | { key: string; status: 'ready'; rows: SessionResultRow[] };

export function WeekendSessionResults({ season, round, eventName, sessions, selected, now }: {
  season: number; round: number; eventName: string; sessions: SessionItem[]; selected: string; now: number;
}) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const fromCalendar = params.get('from') === 'calendar';
  const title = useRef<HTMLHeadingElement>(null);
  const groups = weekendResultGroups(sessions);
  const activeSession = selected || groups[0]?.sessions[0]?.id || '';
  const group = groups.find(item => item.sessions.some(session => session.id === activeSession));
  const session = sessions.find(item => weekendSession(item.name)?.id === activeSession);
  const target = session && weekendSession(session.name);
  const started = session && (sessionStart(session) ?? Infinity) <= now;
  const [state, setState] = useState<State | null>(null);
  const [attempt, setAttempt] = useState(0);
  const path = target?.path;
  const practice = target?.practice;
  const summaryLink = fromCalendar ? `/season?year=${season}&round=${round}&filter=all` : weekendSessionLink(season, round);
  const sessionLink = (name: string) => `${weekendSessionLink(season, round, name)}${fromCalendar ? '&from=calendar' : ''}`;
  const requestKey = `${season}:${round}:${path}:${practice}:${attempt}`;
  const loading = state?.key !== requestKey;

  useEffect(() => { title.current?.focus(); }, []);
  useEffect(() => {
    if (!path || !started) return;
    let active = true;
    apiRequest<Response>(`/api${path}`, { season, round, ...(practice ? { session: practice } : {}) })
      .then(response => {
        if (!active) return;
        setState({ key: requestKey, status: 'ready', rows: matchesWeekendResult(response, season, round, practice) ? response.results || [] : [] });
      })
      .catch(error => { if (active) setState({ key: requestKey, status: 'error', message: error instanceof Error ? error.message : 'Не удалось загрузить результаты.' }); });
    return () => { active = false; };
  }, [path, practice, started, season, round, attempt, requestKey]);

  const options = groups.map(item => ({ value: item.id, label: item.label }));

  return <main className="weekend-page weekend-session-page">
    <header className="weekend-session-header">
      <Link className="weekend-secondary" to={summaryLink}><span aria-hidden="true">←</span> {fromCalendar ? 'К календарю' : 'К уик-энду'}</Link>
    </header>
    <div className="weekend-session-title"><h1 ref={title} tabIndex={-1}>{session ? 'Результаты' : 'Сессия не найдена'}</h1><p>{eventName} · {season} · этап {round}</p></div>
    {groups.length > 0 && <section className="weekend-result-controls" aria-label="Выбор результатов">
      <div className="weekend-session-select"><CustomSelect ariaLabel="Раздел результатов" options={options} value={group?.id || ''}
        onChange={value => { const first = groups.find(item => item.id === value)?.sessions[0]; if (first) navigate(sessionLink(first.session.name), { preventScrollReset: true }); }} /></div>
      {group && <GlassSwitch className="weekend-result-switch" label={`Сессии: ${group.label}`} selected={activeSession} replace
        items={group.sessions.map(item => ({ id: item.id, label: item.label, to: sessionLink(item.session.name) }))} />}

      {session && <p className="weekend-result-session-name">{session.name}</p>}
    </section>}
    {!target || !started ? <p className="weekend-empty" role="status">Результаты этой сессии пока недоступны. Выберите прошедшую сессию или вернитесь к расписанию.</p>
      : loading || !state ? <div className="weekend-result-loading" role="status">Загружаем классификацию…<div aria-hidden="true"><span /><span /><span /></div></div>
      : state.status === 'error' ? <div className="weekend-result-feedback" role="alert"><p>{state.message}</p><button type="button" className="weekend-button" onClick={() => { setAttempt(value => value + 1); }}>Повторить загрузку</button></div>
      : !state.rows.length ? <p className="weekend-empty" role="status">Классификация выбранной сессии ещё не опубликована. Источник может обновить её с задержкой после финиша.</p>
      : <SessionClassification rows={state.rows} kind={(practice ? 'practice' : activeSession) as SessionResultKind} season={season} label={session.name} />}

  </main>;
}
