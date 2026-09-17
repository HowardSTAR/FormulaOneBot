import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { PersonalReview } from './PersonalReview';
import './season-progress.css';

type Round = {season: number; round: number; event_name: string; points: number; max_points: number};
type Progress = {season: number; history: Round[]; best_points: number | null; average_points: number | null;
  place: number | null; place_change: number | null; gap_to_higher: number | null; previous_points: number | null; achievements: string[];
  categories: {label: string; exact: number; known: number}[];
  latest: (Round & {items: {label: string; status: string}[]}) | null};

export function SeasonProgress() {
  const [data, setData] = useState<Progress | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [review, setReview] = useState<{season: number; round: number} | null>(() => {
    const query = new URLSearchParams(window.location.search);
    const season = Number(query.get('reviewSeason'));
    const round = Number(query.get('reviewRound'));
    return Number.isInteger(season) && season >= 1950 && season <= 2100 && Number.isInteger(round) && round >= 1 && round <= 40
      ? {season, round} : null;
  });
  useEffect(() => {
    let active = true;
    apiRequest<Progress>('/api/predictions/personal-season').then(value => {if (active) {setData(value); setError('');}})
      .catch(e => {if (active) setError(String(e.message));});
    return () => {active = false;};
  }, [retry]);
  return <section className="season-progress" aria-label="Моя история прогнозов">
    <h3>Мой сезон {data?.season}</h3>
    {error && <p role="alert">{error} <button onClick={() => setRetry(v => v + 1)}>Повторить</button></p>}
    {!data && !error && <p role="status">Загружаем историю…</p>}
    {data && <>
      {data.latest ? <article>
        <h4>{data.latest.event_name} · {data.latest.points} очк.</h4>
        <p>{data.latest.items.filter(i => i.status === 'exact').map(i => i.label).join(' · ') || 'Посмотрите, как начислены баллы.'}</p>
        {data.latest.items.some(i => ['unavailable', 'unknown'].includes(i.status)) && <p>Часть результатов не подтверждена. Отсутствие данных не считается ошибкой прогноза.</p>}
        {data.previous_points !== null && <p>Предыдущий ваш этап: {data.previous_points} очк. Максимум может отличаться из-за спринта и доступности данных.</p>}
        <button onClick={() => setReview(data.latest)}>Разобрать последний этап →</button>
      </article> : <p>После расчёта вашего первого этапа здесь появятся результаты.</p>}
      <p>Лучший этап: <strong>{data.best_points ?? '—'}</strong> · Среднее: <strong>{data.average_points ?? '—'}</strong> · Место в сезоне: <strong>{data.place ?? '—'}</strong></p>
      {data.place_change !== null && <p>Изменение места после последнего рассчитанного этапа: {data.place_change > 0 ? '+' : ''}{data.place_change}. По текущему пересчитанному зачёту.</p>}
      {data.gap_to_higher !== null && <p>До ближайшего участника с большим числом очков: {data.gap_to_higher}.</p>}
      <details><summary>Точность по категориям</summary>
        <p>Только точные попадания среди подтверждённых результатов; неизвестные исходы исключены.</p>
        {data.categories.map(c => <p key={c.label}>{c.label}: {c.exact} из {c.known} ({Math.round(c.exact / c.known * 100)}%)</p>)}
      </details>
      {data.achievements.length > 0 && <p>Достижения: {data.achievements.join(' · ')}</p>}
      <h4>Мои этапы</h4>
      <div className="season-progress-rounds">{[...data.history].reverse().map(r => <button key={r.round} onClick={() => setReview(r)}>{r.event_name || `Этап ${r.round}`} <strong>{r.points} / {r.max_points}</strong></button>)}</div>
      <Link to="/next-race">Следующий уик-энд →</Link>
    </>}
    {review && <PersonalReview season={review.season} round={review.round} onClose={() => setReview(null)} />}
  </section>;
}
