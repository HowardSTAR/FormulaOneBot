import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { BackButton } from '../../components/BackButton';
import { YearSelect } from '../../components/YearSelect';
import { apiRequest } from '../../helpers/api';
import './history.css';
import { ShareButton } from '../../components/ShareButton';

type Kind = 'drivers' | 'constructors';
type Standing = { id: string; name: string; position: number | null; position_text?: string; points: number; wins: number; round: number; teams: string[] };
type Year = { season: number; status: string; current: boolean; standing: Standing | null };
type Series = { id: string; name: string; seasons: Year[] };
type History = { series: Series[]; years: { season: number; status: string; source: string }[]; note: string; updated_at: string; queryKey?: string };
const colors = ['#ff6259', '#53d2cd', '#e8c971'];
const current = new Date().getFullYear();

function HistoryChart({ series }: { series: Series[] }) {
  const seasons = series[0]?.seasons || [];
  const maxPosition = Math.max(10, ...series.flatMap(s => s.seasons.map(y => y.standing?.position || 0)));
  const x = (i: number) => 50 + i * 620 / Math.max(1, seasons.length - 1);
  const y = (p: number) => 25 + (p - 1) * 210 / Math.max(1, maxPosition - 1);
  return <svg className="history-chart" viewBox="0 0 710 275" role="img" aria-label="Места в чемпионате по сезонам. Первое место сверху; точные значения в таблице ниже.">
    {[1, Math.round(maxPosition / 2), maxPosition].map(p => <g key={p}><line x1="50" x2="670" y1={y(p)} y2={y(p)} stroke="#45454c" /><text x="6" y={y(p) + 4} fill="#b4b4c1">P{p}</text></g>)}
    {seasons.map((year, i) => <text key={year.season} x={x(i)} y="265" textAnchor="middle" fill="#b4b4c1" fontSize="12">{year.season}</text>)}
    {series.map((item, index) => <g key={item.id} fill={colors[index]} stroke={colors[index]}>
      {item.seasons.map((year, i) => {
        const standing = year.standing;
        if (!standing?.position) return null;
        const previous = item.seasons[i - 1]?.standing;
        return <g key={year.season}>
          {previous?.position && <line x1={x(i - 1)} y1={y(previous.position)} x2={x(i)} y2={y(standing.position)} strokeWidth="2" strokeDasharray={year.current ? '5 4' : undefined} />}
          <circle cx={x(i)} cy={y(standing.position)} r="4"><title>{item.name}: {year.season}, P{standing.position}, {standing.points} очк.</title></circle>
        </g>;
      })}
    </g>)}
  </svg>;
}

export default function HistoryPage() {
  const [params] = useSearchParams();
  return <HistorySearch key={params.toString()} />;
}

function HistorySearch() {
  const [params, setParams] = useSearchParams();
  const kind: Kind = params.get('kind') === 'constructors' ? 'constructors' : 'drivers';
  const submittedIds = (params.get('ids') || '').split(',').filter(Boolean).slice(0, 3);
  const idsKey = submittedIds.join(',');
  const [ids, setIds] = useState(submittedIds);
  const minimum = kind === 'drivers' ? 1950 : 1958;
  const validYear = (value: string | null, fallback: number) => value && Number.isInteger(Number(value)) ? Math.max(minimum, Math.min(current, Number(value))) : fallback;
  const submittedStart = validYear(params.get('from'), current - 4);
  const submittedEnd = Math.max(submittedStart, Math.min(submittedStart + 9, validYear(params.get('to'), current)));
  const [rosterYear, setRosterYear] = useState(validYear(params.get('roster'), current));
  const [start, setStart] = useState(submittedStart);
  const [end, setEnd] = useState(submittedEnd);
  const [roster, setRoster] = useState<{ id: string; name: string }[]>([]);
  const [rosterState, setRosterState] = useState('Загрузка участников…');
  const [rosterLoading, setRosterLoading] = useState(true);
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(idsKey));
  const [retry, setRetry] = useState(0);
  const [rosterRetry, setRosterRetry] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(!idsKey);
  useEffect(() => {
    let active = true;
    apiRequest<{ drivers?: { driverId: string; name: string }[]; constructors?: { constructorId: string; name: string }[] }>(`/api/${kind}`, { season: rosterYear })
      .then(response => {
        if (!active) return;
        const entries = kind === 'drivers' ? (response.drivers || []).map(d => ({ id: d.driverId, name: d.name })) : (response.constructors || []).map(t => ({ id: t.constructorId, name: t.name }));
        setRoster(entries.filter(e => e.id));
        setRosterState(entries.length ? '' : 'Зачёт этого сезона недоступен. Выберите другой год.');
        setRosterLoading(false);
      }).catch(() => { if (active) { setRoster([]); setRosterLoading(false); setRosterState('Не удалось загрузить участников. Выберите другой год или повторите.'); } });
    return () => { active = false; };
  }, [kind, rosterYear, rosterRetry]);
  useEffect(() => {
    if (!idsKey) return;
    let active = true;
    apiRequest<History>('/api/standings-history', { kind, ids: idsKey, start_year: submittedStart, end_year: submittedEnd }, 'GET', 150000)
      .then(response => { if (active) { setData(response); setLoading(false); } })
      .catch(e => { if (active) { setError(e instanceof Error ? e.message : 'История недоступна'); setLoading(false); } });
    return () => { active = false; };
  }, [kind, idsKey, submittedStart, submittedEnd, retry]);
  function search() {
    const next = new URLSearchParams({ kind, ids: ids.join(','), from: String(start), to: String(end), roster: String(rosterYear) });
    if (next.toString() === params.toString()) { setError(''); setLoading(true); setRetry(r => r + 1); }
    else setParams(next);
  }
  function select(next: string[]) {
    if (!ids.length && (rosterYear < start || rosterYear > end)) { setStart(Math.max(minimum, rosterYear - 4)); setEnd(rosterYear); }
    setIds(next);
  }
  function changeKind(next: Kind) {
    if (next === kind) return;
    setParams({ kind: next });
  }
  const displayed = data?.series || [];
  const changed = ids.join(',') !== idsKey || start !== submittedStart || end !== submittedEnd;
  return <main className="history-page">
    <BackButton>← Назад</BackButton>
    <header><h1>История чемпионата</h1><p>Рост и спад в зачёте по сезонам: до трёх пилотов или команд. Личный зачёт с 1950 года, Кубок конструкторов с 1958.</p></header>
    <div className="history-tabs" role="group" aria-label="Тип зачёта">
      <button type="button" aria-pressed={kind === 'drivers'} onClick={() => changeKind('drivers')}>Пилоты</button>
      <button type="button" aria-pressed={kind === 'constructors'} onClick={() => changeKind('constructors')}>Команды</button>
    </div>
    <details className="history-panel history-filters" open={filtersOpen} onToggle={event => setFiltersOpen(event.currentTarget.open)}>
      <summary>{ids.length ? `Сравнение · участников: ${ids.length} · ${start}–${end}` : 'Кого сравниваем'} <span>· настроить</span></summary>
      <p className="history-note">Выберите участника и нажмите «Показать сравнение». По умолчанию — последние пять сезонов.</p>
      <form onSubmit={event => { event.preventDefault(); if (ids.length && !loading) search(); }}>
      <div className="history-controls">
        <label>Добавить участника<select value="" disabled={ids.length >= 3 || !roster.length} onChange={e => select([...ids, e.target.value])}>
          <option value="">Выберите…</option>{roster.filter(r => !ids.includes(r.id)).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select></label>
      </div>
      {rosterState && <p role="status" className={rosterLoading ? 'history-loading' : undefined}>{rosterState} {!rosterLoading && <button type="button" onClick={() => { setRosterLoading(true); setRosterState('Загрузка участников…'); setRosterRetry(r => r + 1); }}>Повторить загрузку участников</button>}</p>}
      <div className="history-legend">{ids.map((id, i) => <button type="button" key={id} style={{ borderColor: colors[i] }} onClick={() => select(ids.filter(v => v !== id))} aria-label={`Убрать ${displayed.find(s => s.id === id)?.name || id}`}><span style={{ color: colors[i] }}>●</span> {displayed.find(s => s.id === id)?.name || roster.find(r => r.id === id)?.name || id} ×</button>)}</div>
      <details className="history-advanced"><summary>Период {start}–{end} · состав {rosterYear} · изменить</summary>
      <div className="history-controls"><div><span>Участники из сезона</span><YearSelect ariaLabel="Состав сезона" value={rosterYear} onChange={year => { if (year === rosterYear) return; setRoster([]); setRosterLoading(true); setRosterState('Загрузка участников…'); setRosterYear(year); }} minYear={minimum} maxYear={current} /></div></div>
      <div className="history-controls">
        <div><span>Первый сезон</span><YearSelect ariaLabel="Первый сезон" value={start} minYear={minimum} maxYear={current} onChange={year => { setStart(year); setEnd(Math.min(current, Math.max(year, Math.min(end, year + 9)))); }} showCurrentYearBtn={false} /></div>
        <div><span>Последний сезон</span><YearSelect ariaLabel="Последний сезон" value={end} minYear={Math.max(minimum, start)} maxYear={Math.min(current, start + 9)} onChange={setEnd} showCurrentYearBtn={false} /></div>
      </div><p className="history-note">Можно выбрать до 10 сезонов за один просмотр.</p></details>
      <div className="history-search-actions"><button type="submit" className="history-search-button" disabled={!ids.length || loading}>{loading ? 'Загружаем сравнение…' : 'Показать сравнение'}</button><span>{!ids.length ? 'Добавьте хотя бы одного участника' : `${ids.length} из 3 участников · ${start}–${end}`}</span></div>
      </form>
    </details>
    {!ids.length && <p>Выберите участника. Для исторического пилота сначала смените год состава.</p>}
    {loading && <p role="status" className="history-loading">Загружаем историю {submittedStart}–{submittedEnd}. Первый запрос может занять до двух минут. Повторно нажимать поиск не нужно.</p>}
    {error && <p role="alert">{error} <button type="button" onClick={() => { setError(''); setLoading(true); setRetry(r => r + 1); }}>Повторить поиск</button></p>}
    {data && changed && <p role="status" className="history-note">Параметры изменены. Ниже предыдущий результат; нажмите «Показать сравнение», чтобы обновить его.</p>}
    {data && <section className="history-panel">
      <h2>Место в чемпионате · {submittedStart}–{submittedEnd}</h2><p className="history-note">P1 сверху. Линия прерывается, если записи нет; текущий сезон показан пунктиром.</p>
      <div className="history-chart-legend">{data.series.map((series, i) => <span key={series.id}><span style={{ color: colors[i] }}>●</span> {series.name}</span>)}</div>
      <HistoryChart series={data.series} />
      <ShareButton options={{kind: 'history', history_kind: kind, ids: submittedIds, start_year: submittedStart, end_year: submittedEnd}}>Поделиться сравнением</ShareButton>
      <div className="history-table-scroll"><table className="history-table"><caption>Места, очки и победы в Гран-при по сезонам</caption><thead><tr><th scope="col">Сезон</th>{data.series.map(s => <th scope="col" key={s.id}>{s.name}</th>)}</tr></thead>
        <tbody>{data.years.map(year => <tr key={year.season}><th scope="row"><Link to={`/${kind}?year=${year.season}`}>{year.season}{year.season === current ? ' · идёт' : ''}</Link></th>
          {data.series.map(s => { const standing = s.seasons.find(y => y.season === year.season)?.standing;
            return <td key={s.id}>{standing ? <><strong>{standing.position ? `P${standing.position}` : `Без места (${standing.position_text || '—'})`}</strong> · {standing.points} очк.<small>{standing.wins} побед · после этапа {standing.round}{standing.teams.length ? ` · ${standing.teams.join(', ')}` : ''}</small></> : year.status === 'available' ? 'Нет записи в зачёте' : 'Данные недоступны'}</td>; })}</tr>)}</tbody></table></div>
      <p className="history-note">{data.note}</p><details><summary>Данные по сезонам</summary>{data.years.map(y => <p key={y.season}><a href={y.source} target="_blank" rel="noreferrer">Зачёт {y.season}</a> · {y.status === 'available' ? 'загружено' : 'нет подтверждённых данных'}</p>)}</details>
    </section>}
  </main>;
}
