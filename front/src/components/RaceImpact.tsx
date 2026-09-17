import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../helpers/api';
import { GlossaryText } from './GlossaryText';
type Row = {code: string; name: string; position: number; points: number; grid_position?: number | null; is_favorite_driver?: boolean; is_favorite_team?: boolean};
type Impact = {changes: {code: string; position: number; change: number}[]; note: string};
export function RaceImpact({season, round, rows}: {season: number; round: number; rows: Row[]}) {
  const [data, setData] = useState<Impact | null>(null);
  useEffect(() => {
    let active = true;
    apiRequest<Impact>('/api/race-impact', {season, round_num: round}).then(d => {if (active) setData(d);})
      .catch(() => {if (active) setData({changes: [], note: 'Изменения зачёта временно недоступны.'});});
    return () => {active = false;};
  }, [season, round]);
  const movers = rows.filter(r => r.grid_position != null && r.grid_position > 0 && r.position > 0 && r.grid_position > r.position)
    .sort((a,b) => (b.grid_position! - b.position) - (a.grid_position! - a.position));
  const favorites = rows.filter(r => r.is_favorite_driver || r.is_favorite_team);
  return <details className="prediction-rules"><summary>Что изменилось после этапа</summary>
    <div style={{padding: 16}}>
      {movers[0] && <p>Наибольший прирост позиций среди доступных данных: {movers[0].name}, +{movers[0].grid_position! - movers[0].position} (старт → итоговая классификация).</p>}
      {!movers.length && <p>Нет подтверждённых данных о приросте позиций.</p>}
      {data?.changes.map(c => <p key={c.code}>{c.code}: {c.position}-е место в чемпионате · {c.change > 0 ? '+' : ''}{c.change} поз.</p>)}
      <p>{data?.note || 'Проверяем изменения чемпионата…'}</p>
      {favorites.length > 0 && <p>Ваше избранное: {favorites.map(r => `${r.code} — P${r.position}, ${r.points} очк.`).join(' · ')}</p>}
      <p><Link to={`/predictions?tab=history&reviewSeason=${season}&reviewRound=${round}`}>Как это повлияло на мой прогноз →</Link></p>
      <p><GlossaryText>Разобраться в терминах: машина безопасности, виртуальная машина безопасности, временной штраф.</GlossaryText></p>
    </div>
  </details>;
}
