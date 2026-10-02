import { Link } from 'react-router-dom';
import type { useRaceRecap } from '../helpers/useRaceRecap';
import { GlossaryText } from './GlossaryText';
import { ShareButton } from './ShareButton';
import '../pages/history/history.css';
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
      {!!data?.chronicle?.length && <details className="race-news" aria-label="Ключевые события гонки">
        <summary>Ключевые события гонки</summary>
        <ul>{data.chronicle.slice(0, 4).map(item => <li key={item.url}><GlossaryText>{item.title}</GlossaryText></li>)}</ul>
      </details>}
      {!!data?.news?.length && <details className="race-news" aria-label="Интересные моменты гонки">
        <summary>Интересные моменты гонки</summary>
        <ul>{data.news.slice(0, 3).map(item => <li key={item.url}>
          <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title} ↗</a>
          <small>{item.publisher} · {new Date(item.published_at).toLocaleDateString('ru-RU')}</small>
        </li>)}</ul>
      </details>}
      {favorites.length > 0 && <details><summary>Ваше избранное · {favorites.length}</summary><ul>{favorites.map(row => <li key={row.code}>{row.name} — P{row.position}, {row.points ?? '—'} очк.</li>)}</ul></details>}
      <p><Link className="ui-action-link" to={`/predictions?tab=history&reviewSeason=${season}&reviewRound=${round}`}>Как это повлияло на мой прогноз →</Link></p>
  </section>;
}
