import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { BackButton } from '../../components/BackButton';
import { YearSelect } from '../../components/YearSelect';
import { apiRequest } from '../../helpers/api';
import './history.css';

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
  const [params, setParams] = useSearchParams();
  const kind: Kind = params.get('kind') === 'constructors' ? 'constructors' : 'drivers';
  const ids = (params.get('ids') || '').split(',').filter(Boolean).slice(0, 3);
  const idsKey = ids.join(',');
  const minimum = kind === 'drivers' ? 1950 : 1958;
  const [rosterYear, setRosterYear] = useState(current);
  const [start, setStart] = useState(current - 4);
  const [end, setEnd] = useState(current);
  const [roster, setRoster] = useState<{ id: string; name: string }[]>([]);
  const [rosterState, setRosterState] = useState('Загрузка участников…');
  const queryKey = `${kind}:${idsKey}:${start}:${end}`;
  const [cachedData, setData] = useState<History | null>(null);
  const data = cachedData?.queryKey === queryKey ? cachedData : null;
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(idsKey));
  const [retry, setRetry] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(!idsKey);
  useEffect(() => {
    let active = true;
    apiRequest<{ drivers?: { driverId: string; name: string }[]; constructors?: { constructorId: string; name: string }[] }>(`/api/${kind}`, { season: rosterYear })
      .then(response => {
        if (!active) return;
        const entries = kind === 'drivers' ? (response.drivers || []).map(d => ({ id: d.driverId, name: d.name })) : (response.constructors || []).map(t => ({ id: t.constructorId, name: t.name }));
        setRoster(entries.filter(e => e.id));
        setRosterState(entries.length ? '' : 'Зачёт этого сезона недоступен. Выберите другой год.');
      }).catch(() => { if (active) { setRoster([]); setRosterState('Не удалось загрузить участников. Выберите другой год или повторите.'); } });
    return () => { active = false; };
  }, [kind, rosterYear, retry]);
  useEffect(() => {
    if (!idsKey) return;
    let active = true;
    apiRequest<History>('/api/standings-history', { kind, ids: idsKey, start_year: start, end_year: end }, 'GET', 150000)
      .then(response => { if (active) { setData({ ...response, queryKey }); setLoading(false); } })
      .catch(e => { if (active) { setError(e instanceof Error ? e.message : 'История недоступна'); setLoading(false); } });
    return () => { active = false; };
  }, [kind, idsKey, start, end, retry, queryKey]);
  function reset() { setData(null); setError(''); setLoading(true); }
  function select(next: string[]) {
    reset();
    if (!ids.length && (rosterYear < start || rosterYear > end)) { setStart(Math.max(minimum, rosterYear - 4)); setEnd(rosterYear); }
    setParams({ kind, ids: next.join(',') });
  }
  function changeKind(next: Kind) {
    if (next === kind) return;
    const first = next === 'constructors' ? 1958 : 1950;
    setStart(Math.max(first, start)); setEnd(Math.max(first, end)); setRosterYear(Math.max(first, rosterYear));
    setData(null); setError(''); setLoading(false); setRoster([]); setRosterState('Загрузка участников…'); setParams({ kind: next });
  }
  const displayed = data?.series || [];
  return <main className="history-page">
    <BackButton>← Назад</BackButton>
    <header><h1>История чемпионата</h1><p>Рост и спад в зачёте по сезонам: до трёх пилотов или команд. Личный зачёт с 1950 года, Кубок конструкторов с 1958.</p></header>
    <div className="history-tabs" role="group" aria-label="Тип зачёта">
      <button type="button" aria-pressed={kind === 'drivers'} onClick={() => changeKind('drivers')}>Пилоты</button>
      <button type="button" aria-pressed={kind === 'constructors'} onClick={() => changeKind('constructors')}>Команды</button>
    </div>
    <details className="history-panel history-filters" open={filtersOpen} onToggle={event => setFiltersOpen(event.currentTarget.open)}>
      <summary>{ids.length ? `Сравнение: ${ids.length} участников · ${start}–${end}` : 'Кого сравниваем'} <span>· настроить</span></summary>
      <div className="history-controls"><div><span>Состав сезона</span><YearSelect value={rosterYear} onChange={year => { setRoster([]); setRosterState('Загрузка участников…'); setRosterYear(year); }} minYear={minimum} maxYear={current} /></div>
        <label>Добавить участника<select value="" disabled={ids.length >= 3 || !roster.length} onChange={e => select([...ids, e.target.value])}>
          <option value="">Выберите…</option>{roster.filter(r => !ids.includes(r.id)).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select></label>
      </div>
      {rosterState && <p role="status">{rosterState} <button type="button" onClick={() => setRetry(r => r + 1)}>Повторить</button></p>}
      <div className="history-legend">{ids.map((id, i) => <button type="button" key={id} style={{ borderColor: colors[i] }} onClick={() => select(ids.filter(v => v !== id))} aria-label={`Убрать ${displayed.find(s => s.id === id)?.name || id}`}><span style={{ color: colors[i] }}>●</span> {displayed.find(s => s.id === id)?.name || roster.find(r => r.id === id)?.name || id} ×</button>)}</div>
      <div className="history-controls">
        <div><span>Первый сезон</span><YearSelect value={start} minYear={minimum} maxYear={current} onChange={year => { reset(); setStart(year); setEnd(Math.min(current, Math.max(year, Math.min(end, year + 9)))); }} showCurrentYearBtn={false} /></div>
        <div><span>Последний сезон</span><YearSelect value={end} minYear={Math.max(minimum, start)} maxYear={Math.min(current, start + 9)} onChange={year => { reset(); setEnd(year); }} showCurrentYearBtn={false} /></div>
      </div><p className="history-note">До 10 сезонов за один просмотр — чтобы не перегружать источник. Для более старой эпохи выберите другой первый год.</p>
    </details>
    {!ids.length && <p>Выберите участника. Для исторического пилота сначала смените год состава.</p>}
    {(loading || !data && !error) && ids.length > 0 && <p role="status">Загружаем историю последовательно. Первый запрос может занять до двух минут…</p>}
    {error && <p role="alert">{error} <button type="button" onClick={() => { reset(); setRetry(r => r + 1); }}>Повторить</button></p>}
    {data && <section className="history-panel">
      <h2>Место в чемпионате</h2><p className="history-note">P1 сверху. Линия прерывается, если записи нет; текущий сезон показан пунктиром.</p>
      <div className="history-chart-legend">{data.series.map((series, i) => <span key={series.id}><span style={{ color: colors[i] }}>●</span> {series.name}</span>)}</div>
      <HistoryChart series={data.series} />
      <div className="history-table-scroll"><table className="history-table"><caption>Места, очки и победы в Гран-при по сезонам</caption><thead><tr><th scope="col">Сезон</th>{data.series.map(s => <th scope="col" key={s.id}>{s.name}</th>)}</tr></thead>
        <tbody>{data.years.map(year => <tr key={year.season}><th scope="row"><Link to={`/${kind}?year=${year.season}`}>{year.season}{year.season === current ? ' · идёт' : ''}</Link></th>
          {data.series.map(s => { const standing = s.seasons.find(y => y.season === year.season)?.standing;
            return <td key={s.id}>{standing ? <><strong>{standing.position ? `P${standing.position}` : `Без места (${standing.position_text || '—'})`}</strong> · {standing.points} очк.<small>{standing.wins} побед · после этапа {standing.round}{standing.teams.length ? ` · ${standing.teams.join(', ')}` : ''}</small></> : year.status === 'available' ? 'Нет записи в зачёте' : 'Данные недоступны'}</td>; })}</tr>)}</tbody></table></div>
      <p className="history-note">{data.note}</p><details><summary>Источники и обновление</summary><p>Получено: {new Date(data.updated_at).toLocaleString('ru-RU')}</p>{data.years.map(y => <p key={y.season}><a href={y.source} target="_blank" rel="noreferrer">Jolpica · {y.season}</a> · {y.status === 'available' ? 'загружено' : 'нет подтверждённых данных'}</p>)}</details>
    </section>}
  </main>;
}
