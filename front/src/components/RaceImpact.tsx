import { Link } from 'react-router-dom';
import type { useRaceRecap } from '../helpers/useRaceRecap';
import { GlossaryText } from './GlossaryText';
import { ShareButton } from './ShareButton';
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
      {!!data?.items.length && <p className="history-note">Изменения чемпионата — за весь уик-энд. Первые победы и подиумы — в этом сезоне.</p>}
      {!!data?.items.length && <ShareButton options={{kind: 'recap', season, round}}>Отправить главное о гонке</ShareButton>}
      {favorites.length > 0 && <p>Ваше избранное: {favorites.map(r => `${r.code} — P${r.position}, ${r.points} очк.`).join(' · ')}</p>}
      <p><Link to={`/predictions?tab=history&reviewSeason=${season}&reviewRound=${round}`}>Как это повлияло на мой прогноз →</Link></p>
  </section>;
}
