import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { DriverPortrait } from '../../components/DriverPortrait';
import { TeamLogo } from '../../components/TeamLogo';
import { YearSelect } from '../../components/YearSelect';
import { ShareButton } from '../../components/ShareButton';
import { apiRequest } from '../../helpers/api';
import { CompareParticipantPicker } from '../compare/CompareParticipantPicker';
import { HomeIcon } from '../index/HomeIcon';
import { homeTeamIdentity } from '../index/team-identity';
import '../index/home-team-colors.css';
import '../index/glass-switch.css';
import '../../assets/entrant-highlight.css';
import './history.css';

type Kind = 'drivers' | 'constructors';
type Standing = { id: string; name: string; position: number | null; position_text?: string; points: number; wins: number; round: number; teams: string[] };
type Year = { season: number; status: string; current: boolean; standing: Standing | null };
type Series = { id: string; name: string; seasons: Year[] };
type History = { series: Series[]; years: { season: number; status: string; source: string }[]; note: string; updated_at: string };
type Participant = { id: string; name: string; code?: string; team?: string; imageUrl?: string; season: number };
type Driver = { driverId: string; name: string; code?: string; constructorName?: string; imageUrl?: string };
type Constructor = { constructorId: string; name: string };
const current = new Date().getFullYear();
const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });
const seriesStyle = (index: number) => ({ '--history-series': `var(--history-series-${index})` } as CSSProperties);

function ChartMarker({ index, x, y }: { index: number; x: number; y: number }) {
  if (index === 1) return <rect x={x - 4} y={y - 4} width="8" height="8" rx="1" />;
  if (index === 2) return <path d={`M${x} ${y - 5}l5 5-5 5-5-5Z`} />;
  return <circle cx={x} cy={y} r="4" />;
}

function SeriesKey({ index }: { index: number }) {
  return <svg className="history-series-key" width="28" height="16" viewBox="0 0 28 16" aria-hidden="true" style={seriesStyle(index)}>
    <path d="M0 8h28" fill="none" stroke="currentColor" strokeWidth="2" /><ChartMarker index={index} x={14} y={8} />
  </svg>;
}

function HistoryChart({ series }: { series: Series[] }) {
  const seasons = series[0]?.seasons || [];
  const chart = useRef<HTMLDivElement>(null);
  const [availableWidth, setAvailableWidth] = useState(560);
  // SVG coordinates follow the chart's own size so labels do not inflate on wide screens.
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      const scale = parseFloat(getComputedStyle(document.documentElement).fontSize) / 16;
      setAvailableWidth(entry.contentRect.width / scale);
    });
    if (chart.current) observer.observe(chart.current);
    return () => observer.disconnect();
  }, []);
  const minimumWidth = 240;
  const width = Math.max(minimumWidth, availableWidth);
  const scrolls = availableWidth < minimumWidth;
  const yearStep = Math.max(1, Math.ceil((seasons.length - 1) / Math.max(1, Math.floor((width - 80) / 64))));
  const maxPosition = Math.max(10, ...series.flatMap(item => item.seasons.map(year => year.standing?.position || 0)));
  const x = (index: number) => seasons.length === 1 ? width / 2 : 48 + index * (width - 80) / (seasons.length - 1);
  const y = (position: number) => 24 + (position - 1) * 216 / Math.max(1, maxPosition - 1);
  return <div ref={chart} className="history-chart-scroll" role={scrolls ? 'region' : undefined} aria-label={scrolls ? 'График мест по сезонам, прокручивается по горизонтали' : undefined} tabIndex={scrolls ? 0 : undefined}>
    <svg className="history-chart" viewBox={`0 0 ${width} 284`} style={{ minWidth: `${minimumWidth / 16}rem` }} role="img" aria-label="Места в чемпионате по сезонам. Первое место сверху; точные значения в таблице ниже.">
      {[...new Set([1, 5, 10, maxPosition])].map(position => <g key={position} className="history-chart-axis">
        <line x1="48" x2={width - 24} y1={y(position)} y2={y(position)} /><text x="0" y={y(position) + 4}>P{position}</text>
      </g>)}
      {seasons.map((year, index) => (index % yearStep === 0 && index < seasons.length - yearStep / 2 || index === seasons.length - 1) && <text className="history-chart-year" key={year.season} x={x(index)} y="275" textAnchor="middle">{year.season}</text>)}
      {series.map((item, index) => <g key={item.id} className="history-chart-series" style={seriesStyle(index)}>
        {item.seasons.map((year, seasonIndex) => {
          const standing = year.standing;
          if (!standing?.position) return null;
          const previous = item.seasons[seasonIndex - 1]?.standing;
          return <g key={year.season}>
            {previous?.position && <line x1={x(seasonIndex - 1)} y1={y(previous.position)} x2={x(seasonIndex)} y2={y(standing.position)} strokeWidth="2.5" strokeDasharray={year.current ? '6 5' : undefined} vectorEffect="non-scaling-stroke" />}
            <g><title>{item.name}: {year.season}, P{standing.position}, {numberFormat.format(standing.points)} очк.</title><ChartMarker index={index} x={x(seasonIndex)} y={y(standing.position)} /></g>
          </g>;
        })}
      </g>)}
    </svg>
  </div>;
}

export default function HistoryPage() {
  const [params, setParams] = useSearchParams();
  const kind: Kind = params.get('kind') === 'constructors' ? 'constructors' : 'drivers';
  // Keep the lens mounted across query changes so its transform can interpolate.
  // The search form below still resets its draft and cancels old requests by key.
  return <div className="history-page">
    <header className="history-heading">
      <h1>История чемпионата</h1>
      <p>Как менялась борьба за титул. Сравните места пилотов и команд по сезонам.</p>
    </header>
    <div className="history-section-top">
      <div className="history-tabs" role="group" aria-label="Тип зачёта" style={{ '--section-count': 2, '--section-position': kind === 'drivers' ? 0 : 1 } as CSSProperties}>
        <span className="history-tabs-decoration" aria-hidden="true"><span className="home-section-lens" /></span>
        <button type="button" aria-pressed={kind === 'drivers'} onClick={() => { if (kind !== 'drivers') setParams({ kind: 'drivers' }); }}><HomeIcon name="drivers" />Пилоты</button>
        <button type="button" aria-pressed={kind === 'constructors'} onClick={() => { if (kind !== 'constructors') setParams({ kind: 'constructors' }); }}><HomeIcon name="teams" />Команды</button>
      </div>
      <Link className="history-standing-link" to={`/${kind}`}>{kind === 'drivers' ? 'Личный зачёт с 1950 года' : 'Кубок конструкторов с 1958 года'}<HomeIcon name="chevronRight" /></Link>
    </div>
    <HistorySearch key={params.toString()} />
  </div>;
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
  const [roster, setRoster] = useState<Participant[]>([]);
  const [selectedParticipants, setSelectedParticipants] = useState<Participant[]>([]);
  const [rosterState, setRosterState] = useState('Загрузка участников…');
  const [rosterLoading, setRosterLoading] = useState(true);
  const [rosterError, setRosterError] = useState(false);
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(idsKey));
  const [retry, setRetry] = useState(0);
  const [rosterRetry, setRosterRetry] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(!idsKey);
  const [pickerOpen, setPickerOpen] = useState(false);
  const addButton = useRef<HTMLButtonElement>(null);
  const selection = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    let active = true;
    apiRequest<{ drivers?: Driver[]; constructors?: Constructor[] }>(`/api/${kind}`, { season: rosterYear })
      .then(response => {
        if (!active) return;
        const entries = kind === 'drivers'
          ? (response.drivers || []).map(driver => ({ id: driver.driverId, name: driver.name, code: driver.code, team: driver.constructorName, imageUrl: driver.imageUrl, season: rosterYear }))
          : (response.constructors || []).map(team => ({ id: team.constructorId, name: team.name, season: rosterYear }));
        const available = entries.filter(entry => entry.id);
        setRoster(available);
        setRosterError(false);
        setRosterState(available.length ? '' : 'Зачёт этого сезона недоступен. Выберите другой год состава.');
        setRosterLoading(false);
      }).catch(() => { if (active) { setRoster([]); setRosterLoading(false); setRosterError(true); setRosterState('Не удалось загрузить участников. Выберите другой год или повторите.'); } });
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
    if (next.toString() === params.toString()) { setError(''); setLoading(true); setRetry(value => value + 1); }
    else setParams(next);
  }
  function select(next: string[]) {
    if (!ids.length && (rosterYear < start || rosterYear > end)) { setStart(Math.max(minimum, rosterYear - 4)); setEnd(rosterYear); }
    setIds(next.slice(0, 3));
  }
  function closePicker() {
    setPickerOpen(false);
    requestAnimationFrame(() => { if (addButton.current && !addButton.current.disabled) addButton.current.focus(); else selection.current?.focus(); });
  }
  function participant(id: string): Participant {
    const series = data?.series.find(item => item.id === id);
    const lastEntry = series?.seasons.filter(year => year.standing).at(-1);
    return selectedParticipants.find(item => item.id === id) || roster.find(item => item.id === id)
      || { id, name: series?.name || id, season: lastEntry?.season || rosterYear, team: lastEntry?.standing?.teams.join(', ') };
  }
  const changed = ids.join(',') !== idsKey || start !== submittedStart || end !== submittedEnd;
  const hasPositions = data?.series.some(item => item.seasons.some(year => year.standing?.position));
  const available = roster.filter(item => !ids.includes(item.id));
  return <>
    <details ref={selection} tabIndex={-1} className="history-filters" open={filtersOpen} onToggle={event => setFiltersOpen(event.currentTarget.open)}>
      <summary><span>Участники и период<small>{ids.length ? `${ids.length} из 3 участников · ${start}–${end}` : 'До 3 участников за 10 сезонов'}</small></span><HomeIcon name="chevronDown" /></summary>
      <form onSubmit={event => { event.preventDefault(); if (ids.length && !loading) search(); }}>
        <div className="history-roster-tools">
          <div className="history-field"><span >Состав сезона</span><YearSelect ariaLabel="Состав сезона" value={rosterYear} onChange={year => { if (year === rosterYear) return; setRoster([]); setRosterLoading(true); setRosterError(false); setRosterState('Загрузка участников…'); setRosterYear(year); }} minYear={minimum} maxYear={current} showCurrentYearBtn={false} /></div>
          <button ref={addButton} type="button" className="history-add" disabled={ids.length >= 3 || !available.length} onClick={() => setPickerOpen(true)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>{kind === 'drivers' ? 'Добавить пилотов' : 'Добавить команды'}</button>
          <p className="history-note history-roster-note">Для участника из прошлого выберите год его выступления.</p>
        </div>
        {rosterState && <div role={rosterError ? 'alert' : 'status'} className={`history-status${rosterLoading ? ' history-loading' : ''}`}><p>{rosterState}</p>{rosterError && <button type="button" onClick={() => { setRosterLoading(true); setRosterError(false); setRosterState('Загрузка участников…'); setRosterRetry(value => value + 1); }}>Повторить загрузку участников</button>}</div>}
        {ids.length > 0 && <ul className="history-participants" aria-label="Выбранные участники">{ids.map((id, index) => {
          const item = participant(id);
          return <li key={id} className="history-participant entrant-highlight" data-team={homeTeamIdentity(kind === 'constructors' ? id : '', kind === 'constructors' ? item.name : item.team || '')}>
            {kind === 'drivers' ? <DriverPortrait key={`${item.season}:${id}`} code={item.code} name={item.name} season={item.season} src={item.imageUrl} /> : <TeamLogo key={`${item.season}:${id}`} name={item.name} id={id} season={item.season} />}
            <div><SeriesKey index={index} /><strong>{item.name}</strong>{item.team && <small>{item.team}</small>}</div>
            <button type="button" className="history-remove" onClick={() => select(ids.filter(value => value !== id))} aria-label={`Убрать ${item.name}`}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
          </li>;
        })}</ul>}
        <div className="history-period">
          <div className="history-field"><span>Первый сезон</span><YearSelect ariaLabel="Первый сезон" value={start} minYear={minimum} maxYear={current} onChange={year => { setStart(year); setEnd(Math.min(current, Math.max(year, Math.min(end, year + 9)))); }} showCurrentYearBtn={false} /></div>
          <div className="history-field"><span>Последний сезон</span><YearSelect ariaLabel="Последний сезон" value={end} minYear={Math.max(minimum, start)} maxYear={Math.min(current, start + 9)} onChange={setEnd} showCurrentYearBtn={false} /></div>
          <button type="submit" className="history-search-button" disabled={!ids.length || loading}>{loading ? 'Загружаем сравнение…' : 'Показать сравнение'}</button>
        </div>
      </form>
    </details>
    {pickerOpen && <CompareParticipantPicker season={rosterYear} teamMode={kind === 'constructors'} maxSelection={3 - ids.length}
      options={available.map(item => ({ code: item.id, portraitCode: item.code, name: item.name, team: item.team, imageUrl: item.imageUrl }))}
      onAdd={chosen => { setSelectedParticipants(previous => [...previous.filter(item => !chosen.includes(item.id)), ...roster.filter(item => chosen.includes(item.id))]); select([...ids, ...chosen]); closePicker(); }} onClose={closePicker} />}
    {loading && <div role="status" className="history-status history-loading"><div><h2>Загружаем историю {submittedStart}–{submittedEnd}…</h2><p>Первый запрос может занять до двух минут.</p></div></div>}
    {error && <div role="alert" className="history-status history-error"><div><h2>Не удалось загрузить историю</h2><p>{error}</p></div><button type="button" onClick={() => { setError(''); setLoading(true); setRetry(value => value + 1); }}>Повторить поиск</button></div>}
    {data && changed && <p role="status" className="history-change-note">Параметры изменены. Ниже предыдущий результат; нажмите «Показать сравнение», чтобы обновить его.</p>}
    {data && <section className="history-results" aria-labelledby="history-results-title">
      <div className="history-result-heading"><div><h2 id="history-results-title">Место в чемпионате <span>{submittedStart}–{submittedEnd}</span></h2><p className="history-note">P1 сверху. Пропуск — нет записи; пунктир — текущий сезон.</p></div><ShareButton options={{ kind: 'history', history_kind: kind, ids: submittedIds, start_year: submittedStart, end_year: submittedEnd }}>Поделиться сравнением</ShareButton></div>
      <div className="history-chart-legend">{data.series.map((item, index) => <span key={item.id}><SeriesKey index={index} />{item.name}</span>)}</div>
      {hasPositions ? <HistoryChart series={data.series} /> : <div role="status" className="history-empty"><HomeIcon name="history" /><h3>Нет мест за выбранный период</h3><p>Измените участников или период. Доступность каждого сезона указана в таблице.</p></div>}
      <div className="history-table-scroll" role="region" aria-label="Точные результаты по сезонам" tabIndex={0}>
        <table className="history-table" role="table">
          <caption>Места, очки и победы в Гран-при по сезонам</caption>
          <thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">Сезон</th>{data.series.map((item, index) => <th scope="col" role="columnheader" id={`history-column-${index}`} key={item.id}><span className="history-table-name"><SeriesKey index={index} />{item.name}</span></th>)}</tr></thead>
          <tbody role="rowgroup">{data.years.map(year => <tr role="row" key={year.season} data-current={year.season === current || undefined}>
            <th scope="row" role="rowheader" id={`history-season-${year.season}`}>
              <Link to={`/${kind}?year=${year.season}`}>{year.season}<small>{year.status !== 'available' ? 'Нет данных' : year.season === current ? 'Сезон идёт' : 'Итог сезона'}</small></Link>
              <span className="history-mobile-column" aria-hidden="true">Место</span><span className="history-mobile-column" aria-hidden="true">Очки</span>
            </th>
            {data.series.map((item, index) => {
              const standing = item.seasons.find(value => value.season === year.season)?.standing;
              return <td role="cell" key={item.id} headers={`history-season-${year.season} history-column-${index}`}>
                <span className="history-mobile-entrant" aria-hidden="true"><SeriesKey index={index} /><strong>{item.name}</strong></span>
                {standing ? <>
                  <div className="history-table-score"><strong>{standing.position ? `P${standing.position}` : `Без места (${standing.position_text || '—'})`}</strong><span>{numberFormat.format(standing.points)}<span className="history-points-unit"> очк.</span></span></div>
                  <small className="history-table-meta">Победы: {standing.wins} · после этапа {standing.round}{standing.teams.length ? ` · ${standing.teams.join(', ')}` : ''}</small>
                </> : <span className="history-missing">{year.status === 'available' ? 'Нет записи в зачёте' : 'Данные недоступны'}</span>}
              </td>;
            })}
          </tr>)}</tbody>
        </table>
      </div>
      <p className="history-note history-source-note">{data.note}</p><details className="history-sources"><summary>Источники по сезонам<HomeIcon name="chevronDown" /></summary><ul>{data.years.map(year => <li key={year.season}><a href={year.source} target="_blank" rel="noreferrer">Зачёт {year.season}</a><span>{year.status === 'available' ? 'Загружено' : 'Нет подтверждённых данных'}</span></li>)}</ul></details>
    </section>}
  </>;
}
