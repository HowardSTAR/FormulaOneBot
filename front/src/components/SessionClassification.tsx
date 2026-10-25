import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../helpers/api';
import { resultStatus } from '../helpers/presentation';
import { classificationRows, lapMilliseconds, practiceGap, type SessionResultKind, type SessionResultRow } from '../helpers/sessionClassification';
import { homeTeamIdentity } from '../pages/index/team-identity';
import '../pages/index/home-team-colors.css';
import './session-classification.css';
import { DriverPortrait } from './DriverPortrait';

type Driver = { code: string; constructorName?: string; imageUrl?: string };

export function SessionClassification({ rows: source, kind, season, label }: { rows: SessionResultRow[]; kind: SessionResultKind; season: number; label: string }) {
  const rows = classificationRows(source, kind);
  const [teams, setTeams] = useState<{ season: number; drivers: Driver[] } | null>(null);
  useEffect(() => {
    let active = true;
    apiRequest<{ drivers?: Driver[] }>('/api/drivers', { season }).then(response => {
      if (active) setTeams({ season, drivers: response.drivers || [] });
    }).catch(() => { /* The classification remains usable without optional team metadata. */ });
    return () => { active = false; };
  }, [season]);
  const qualifying = kind === 'quali' || kind === 'sprint-quali';
  const race = kind === 'race' || kind === 'sprint';
  const hasLaps = source.some(row => row.laps !== undefined);
  if (!rows.length) return <p className="weekend-empty" role="status">В этой сессии пока нет опубликованных кругов.</p>;
  return <ol className="session-classification" aria-label={`Классификация: ${label}`}>
    {rows.map((row, index) => {
      const rawCode = row.code || row.driver;
      const code = rawCode && !['?', '-', '—'].includes(rawCode) ? rawCode : undefined;
      const name = row.name || code || 'Пилот не указан';
      const driver = teams?.season === season ? teams.drivers.find(driver => driver.code.toUpperCase() === code?.toUpperCase()) : undefined;
      const team = row.team || driver?.constructorName;
      const position = kind === 'practice' && lapMilliseconds(row.best) !== null ? index + 1 : row.position;
      const metrics = kind === 'practice' ? [
        { label: 'Лучший круг', value: row.best || '—' },
        { label: 'От лидера', value: practiceGap(row, rows[0]) },
        { label: 'Круги', value: row.laps ?? '—' },
      ] : qualifying ? [
        { label: 'Лучший круг', value: row.best || '—' },
        { label: 'Сегмент', value: row.segment || '—', segment: true },
      ] : [
        { label: 'Время / статус', value: row.time || row.gap || resultStatus(row.status) },
        ...(hasLaps ? [{ label: 'Круги', value: row.laps ?? '—' }] : []),
        { label: 'Очки', value: row.points ?? '—' },
      ];
      const content = <>
        <span className="session-result-position" aria-label={position > 0 ? `Позиция ${position}` : 'Без позиции'}>{position > 0 ? String(position).padStart(2, '0') : '—'}</span>
        <DriverPortrait key={`${season}:${code}:${driver?.imageUrl || ''}`} code={code} name={name} season={season} src={driver?.imageUrl} className="session-driver-portrait" />
        <div className="session-result-identity"><h2>{name}{row.is_favorite_driver && <span className="session-result-favorite" aria-label="Избранный пилот">★</span>}</h2><p>{team || code || '—'}</p></div>
        <dl className="session-result-metrics">{metrics.map(metric => <div key={metric.label}><dt>{metric.label}</dt><dd>{'segment' in metric ? <span className="session-quali-segment" data-segment={row.segment}>{metric.value}</span> : metric.value}</dd></div>)}</dl>
        {code && <svg className="session-result-chevron" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>}
      </>;
      const segmentStart = qualifying && row.segment !== rows[index - 1]?.segment;
      return <li key={`${code || name}:${index}`} data-team={homeTeamIdentity('', team || '')} data-segment-start={segmentStart || undefined}>
        {segmentStart && row.segment && <p className="session-segment-heading">{row.segment}<span>Последний сегмент</span></p>}
        {code ? <Link className={`session-result-row entrant-highlight${race ? ' is-race' : ''}`} to={`/driver-details?code=${encodeURIComponent(code)}&season=${season}`}>{content}</Link> : <div className="session-result-row entrant-highlight has-no-code">{content}</div>}
      </li>;
    })}
  </ol>;
}
