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
    {board.entries.length ? <table className="supporter-league-table" role="table">
      <caption className="supporter-league-sr">Зачёт подписчиков TurboTears, сезон {board.season}</caption>
      <thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">Место</th><th role="columnheader" scope="col">Участник</th><th role="columnheader" scope="col">Баллы</th><th role="columnheader" scope="col">Этапы</th><th role="columnheader" scope="col">Победы</th><th role="columnheader" scope="col">Лучший</th></tr></thead>
      <tbody role="rowgroup">{board.entries.map(entry => <tr role="row" key={entry.user_id} className={entry.user_id === board.current_user_id ? 'supporter-league-me' : undefined}>
        <td role="cell" className={`supporter-league-rank supporter-league-rank-${entry.place}`}><span>{entry.place}</span></td>
        <th role="rowheader" scope="row"><Link to={`/profile/${entry.user_id}?season=${board.season}`}><span>{entry.display_name}</span><SupporterBadge tierName={entry.tier_name} /></Link>{entry.user_id === board.current_user_id && <small>Это ты</small>}</th>
        <td role="cell" className="supporter-league-points"><span className="supporter-league-mobile-label" aria-hidden="true">Баллы</span><strong>{entry.total_points}</strong></td>
        <td role="cell" className="supporter-league-detail">{entry.rounds_scored}</td>
        <td role="cell" className="supporter-league-detail">{entry.wins}</td>
        <td role="cell" className="supporter-league-detail">{entry.best_points}</td>
        <td role="cell" colSpan={3} className="supporter-league-mobile-metrics"><dl>
          <div><dt>Этапы</dt><dd>{entry.rounds_scored}</dd></div>
          <div><dt>Победы</dt><dd>{entry.wins}</dd></div>
          <div><dt>Лучший этап</dt><dd>{entry.best_points}</dd></div>
        </dl></td>
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
