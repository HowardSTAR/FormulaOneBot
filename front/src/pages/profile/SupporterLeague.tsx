import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import SupporterBadge from '../../components/SupporterBadge';
import './supporter-league.css';

type Entry = {
  user_id: number; display_name: string; tier_name: string; place: number;
  total_points: number; rounds_scored: number; wins: number; best_points: number;
};
type Board = { season: number; current_user_id: number; entries: Entry[] };

function Standings({ board }: { board: Board }) {
  const me = board.entries.find(entry => entry.user_id === board.current_user_id);
  return <div className="supporter-league-results">
    <div className="supporter-league-stats">
      <div><span>Твоё место</span><strong>{me ? `#${me.place}` : '—'}</strong></div>
      <div><span>Твои баллы</span><strong>{me?.total_points ?? '—'}</strong></div>
      <div><span>Участников</span><strong>{board.entries.length}</strong></div>
    </div>
    {!me && <p className="profile-muted">Сделай первый прогноз, чтобы появиться в зачёте клуба. <Link to="/predictions">К прогнозам →</Link></p>}
    {board.entries.length ? <table className="supporter-league-table">
      <caption className="supporter-league-sr">Зачёт подписчиков TurboTears, сезон {board.season}</caption>
      <thead><tr><th scope="col">Место</th><th scope="col">Участник</th><th scope="col">Баллы</th><th scope="col">Этапы</th><th scope="col">Победы</th><th scope="col">Лучший</th></tr></thead>
      <tbody>{board.entries.map(entry => <tr key={entry.user_id} className={entry.user_id === board.current_user_id ? 'supporter-league-me' : undefined}>
        <td className={`supporter-league-rank supporter-league-rank-${entry.place}`}><span>{entry.place}</span></td>
        <th scope="row"><Link to={`/profile/${entry.user_id}?season=${board.season}`}>{entry.display_name}<SupporterBadge tierName={entry.tier_name} /></Link>{entry.user_id === board.current_user_id && <small>Это ты</small>}</th>
        <td className="supporter-league-points" data-label="Баллы">{entry.total_points}</td>
        <td data-label="Этапы">{entry.rounds_scored}</td><td data-label="Победы">{entry.wins}</td><td data-label="Лучший">{entry.best_points}</td>
      </tr>)}</tbody>
    </table> : <p className="profile-muted">Сезон клуба начинается с первого прогноза. Твоё место уже ждёт.</p>}
    <details className="supporter-league-rules"><summary>Как устроена лига</summary>
      <p>Все действующие подписчики уровней «На старт», «Свой стиль» и «Полный газ» участвуют в одном зачёте. Вступать отдельно не нужно.</p>
      <p>Баллы начисляются за обычные прогнозы выбранного сезона. Победа на этапе — лучший положительный результат среди участников клуба; при равенстве она засчитывается каждому.</p>
      <p>Выше тот, у кого больше баллов, затем побед, затем лучший результат этапа. При полном равенстве — по имени. Пока подписка неактивна, участник не отображается в клубе; его прогнозы сохраняются.</p>
    </details>
  </div>;
}

function MemberLeague({ season }: { season: number }) {
  const [open, setOpen] = useState(false);
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    // Warm the private standings while the participant reads their profile.
    apiRequest<Board>('/api/profiles/supporters', { season }).then(value => {
      if (active) setBoard(value);
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Не удалось загрузить зачёт'); });
    return () => { active = false; };
  }, [season, attempt]);
  return <>
    <button type="button" className="profile-primary" aria-expanded={open} aria-controls="supporter-league-board" onClick={() => setOpen(value => !value)}>{open ? 'Скрыть зачёт' : `Показать зачёт · ${season}`}</button>
    {open && <div id="supporter-league-board" className="supporter-league-board" aria-busy={!board && !error}>
      {error ? <div className="supporter-league-error"><p role="alert">{error}</p><button type="button" onClick={() => { setError(''); setAttempt(value => value + 1); }}>Повторить загрузку</button></div>
        : board ? <Standings board={board} /> : <div className="supporter-league-loading" role="status"><span>Загружаем зачёт клуба…</span><div aria-hidden="true" /><div aria-hidden="true" /><div aria-hidden="true" /></div>}
    </div>}
  </>;
}

export default function SupporterLeague({ season, supporter }: { season: number; supporter: boolean }) {
  return <section className="profile-panel supporter-league" data-profile-guide="club">
    <div className="supporter-league-heading"><div><p className="supporter-league-eyebrow">ЛИГА ПОДПИСЧИКОВ · {season}</p><h2>Клуб TurboTears</h2></div><SupporterBadge large /></div>
    <p className="profile-muted">Твой круг соперников. Общий зачёт прогнозов за сезон для уровней «На старт», «Свой стиль» и «Полный газ».</p>
    {supporter ? <MemberLeague key={season} season={season} /> : <div className="supporter-league-join"><p>Подписка открывает клубный зачёт и золотой значок рядом с именем.</p><a href="https://boosty.to/turbotears" target="_blank" rel="noopener noreferrer">Присоединиться на Boosty →</a></div>}
  </section>;
}
