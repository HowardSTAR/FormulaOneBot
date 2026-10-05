import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { PersonalReview } from './PersonalReview';
import './season-progress.css';
import { ShareButton } from '../../components/ShareButton';

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
    <header className="season-progress-heading"><div><span className="season-progress-kicker">История прогнозов</span><h3>Мой сезон {data?.season}</h3></div>{data && <span className="season-progress-count">Рассчитано этапов: {data.history.length}</span>}</header>
    {error && <div className="season-progress-error" role="alert"><p>{error}</p><button onClick={() => setRetry(v => v + 1)}>Повторить</button></div>}
    {!data && !error && <p role="status">Загружаем историю…</p>}
    {data && <>
      {data.latest ? <article className="season-progress-latest">
        <header><div><span className="season-progress-kicker">Последний рассчитанный этап</span><h4>{data.latest.event_name}</h4></div><p className="season-progress-score"><strong>{data.latest.points}</strong><span>/ {data.latest.max_points} баллов</span></p></header>
        <p>{data.latest.items.some(i => i.status === 'exact') ? `Точно угадано: ${data.latest.items.filter(i => i.status === 'exact').map(i => i.label).join(' · ')}.` : 'Посмотрите, как начислены баллы по каждой категории.'}</p>
        {data.latest.items.some(i => ['unavailable', 'unknown'].includes(i.status)) && <p>Часть результатов не подтверждена. Отсутствие данных не считается ошибкой прогноза.</p>}
        {data.previous_points !== null && <p className="season-progress-note">Предыдущий этап: {data.previous_points} баллов. Максимум зависит от спринта и подтверждённых данных.</p>}
        <div className="season-progress-actions"><button className="season-progress-primary" onClick={() => setReview(data.latest)}>Разобрать последний этап <span aria-hidden="true">→</span></button><ShareButton options={{kind: 'prediction', season: data.latest.season, round: data.latest.round}} /></div>
      </article> : <p>После расчёта вашего первого этапа здесь появятся результаты.</p>}
      <dl className="season-progress-metrics"><div><dt>Лучший этап</dt><dd>{data.best_points ?? '—'}<small>баллов</small></dd></div><div><dt>Среднее за этап</dt><dd>{data.average_points ?? '—'}<small>баллов</small></dd></div><div><dt>Место в сезоне</dt><dd>{data.place ?? '—'}<small>в общем зачёте</small></dd></div></dl>
      {(data.place_change !== null || data.gap_to_higher !== null) && <div className="season-progress-standing">
        {data.place_change !== null && <p>{data.place_change === 0 ? 'Место не изменилось после последнего этапа.' : `Изменение места после последнего этапа: ${data.place_change > 0 ? '+' : ''}${data.place_change}.`}</p>}
        {data.gap_to_higher !== null && <p>До участника выше в зачёте: <strong>{data.gap_to_higher} баллов</strong>.</p>}
        <small>По текущему пересчитанному зачёту.</small>
      </div>}
      <details className="season-progress-accuracy"><summary>Точность по категориям</summary>
        <p>Только точные попадания среди подтверждённых результатов; неизвестные исходы исключены.</p>
        <dl>{data.categories.map(c => <div key={c.label}><dt>{c.label}</dt><dd>{c.known > 0 ? `${c.exact} из ${c.known} · ${Math.round(c.exact / c.known * 100)}%` : 'Ещё нет результатов'}</dd></div>)}</dl>
      </details>
      {data.achievements.length > 0 && <div className="season-progress-achievements"><span className="season-progress-kicker">Достижения</span><ul>{data.achievements.map(achievement => <li key={achievement}><span aria-hidden="true">✦</span>{achievement}</li>)}</ul></div>}
      <section className="season-progress-history" aria-labelledby="season-rounds-title"><header><h4 id="season-rounds-title">Мои этапы</h4><span>Нажмите на этап для разбора</span></header>
        <div className="season-progress-rounds">{[...data.history].reverse().map(r => <button key={`${r.season}:${r.round}`} onClick={() => setReview(r)}><span><small>Этап {r.round}</small><span>{r.event_name || `Этап ${r.round}`}</span></span><strong>{r.points}<small> / {r.max_points}</small><span aria-hidden="true">↗</span></strong></button>)}</div>
        {data.history.length === 0 && <p>Рассчитанные этапы появятся здесь после гонки.</p>}
      </section>
      <Link className="ui-action-link season-progress-next" to="/next-race">Следующий уик-энд →</Link>
    </>}
    {review && <PersonalReview season={review.season} round={review.round} onClose={() => setReview(null)} />}
  </section>;
}
