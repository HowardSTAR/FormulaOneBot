import { Link } from 'react-router-dom';
import type { useRaceRecap } from '../helpers/useRaceRecap';
import { GlossaryText } from './GlossaryText';
type Row = {code: string; name: string; position: number; points: number; grid_position?: number | null; is_favorite_driver?: boolean; is_favorite_team?: boolean};
export function RaceImpact({season, round, rows, recap}: {season: number; round: number; rows: Row[]; recap: ReturnType<typeof useRaceRecap>}) {
  const {data, error, reload} = recap;
  const favorites = rows.filter(r => r.is_favorite_driver || r.is_favorite_team);
  return <section className="race-recap-panel" aria-label="Короткий рекап гонки">
      <h2>Главное после гонки</h2>
      {!data && !error && <p role="status">Проверяем классификацию и изменения чемпионата…</p>}
      {error && <p role="alert">Рекап временно недоступен. <button type="button" onClick={reload}>Повторить</button></p>}
      {data?.status === 'waiting' && <p>{data.note}</p>}
      {data?.status === 'partial' && <p className="history-note">Часть данных о чемпионате недоступна. Показаны только подтверждённые факты.</p>}
      {data && data.status !== 'ready' && <button type="button" onClick={reload}>Проверить обновление</button>}
      {!!data?.items.length && <div className="race-recap-list">{data.items.map(item => <article key={item.category}><h3>{item.title}</h3><p><GlossaryText>{item.text}</GlossaryText></p></article>)}</div>}
      <details><summary>Источники и как читать сводку</summary>
        <p className="history-note">{data?.note || 'Сводка по правилам, без ИИ. Причины событий не выводятся из очков.'}</p>
        {data?.updated_at && <p>Сформировано: {new Date(data.updated_at).toLocaleString('ru-RU')}</p>}
        {data?.sources?.map(source => <p key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></p>)}
        <p><GlossaryText>Разобраться в терминах: машина безопасности, виртуальная машина безопасности, временной штраф.</GlossaryText></p>
      </details>
      {favorites.length > 0 && <p>Ваше избранное: {favorites.map(r => `${r.code} — P${r.position}, ${r.points} очк.`).join(' · ')}</p>}
      <p><Link to={`/predictions?tab=history&reviewSeason=${season}&reviewRound=${round}`}>Как это повлияло на мой прогноз →</Link></p>
  </section>;
}
