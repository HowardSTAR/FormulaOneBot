import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import './season-progress.css';

type League = {id: number; name: string; owner: boolean; invite_token: string | null};
export type ScoreEntry = {user_id: number; display_name: string; total_points: number; place_change?: number | null; history: {round: number; points: number}[]};
export function StageScores({entries, round}: {entries: ScoreEntry[]; round: number}) {
  const sorted = entries.flatMap(e => {
    const r = e.history.find(h => h.round === round);
    return r ? [{...e, points: r.points}] : [];
  }).sort((a,b) => b.points - a.points || a.display_name.localeCompare(b.display_name));
  return <ol className="league-score-list">{sorted.map((e) => <li key={e.user_id}><strong>#{sorted.findIndex(s => s.points === e.points) + 1}</strong> {e.display_name} <b>{e.points} очк.</b></li>)}{!sorted.length && <li>Результатов этого этапа пока нет.</li>}</ol>;
}

export function LeaguePanel() {
  const [leagues, setLeagues] = useState<League[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [scores, setScores] = useState<{entries: ScoreEntry[]; rounds: {round: number; event_name: string}[]; season: number} | null>(null);
  const [round, setRound] = useState(0);
  const [name, setName] = useState('');
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('invite') || '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest<{leagues: League[]}>('/api/predictions/leagues').then(d => {if (active) setLeagues(d.leagues);}).catch(e => {if (active) setError(e.message);});
    return () => {active = false;};
  }, [version]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    apiRequest<NonNullable<typeof scores>>(`/api/predictions/leagues/${selected}`).then(d => {if (active) setScores(d);}).catch(e => {if (active) setError(e.message);});
    return () => {active = false;};
  }, [selected, version]);
  const action = async (path: string, body: Record<string, string>) => {
    setBusy(true); setError('');
    try {await apiRequest(path, body, 'POST'); setVersion(v => v + 1); setScores(null); setSelected(null);}
    catch (e) {setError(e instanceof Error ? e.message : 'Не удалось выполнить действие');}
    finally {setBusy(false);}
  };
  return <section className="season-progress">
    <h3>Приватные лиги</h3>
    <p>Сравнивайте очки с друзьями. Ответы ваших прогнозов остаются личными. В зачёт входят результаты сезона, в том числе до вступления.</p>
    {error && <p role="alert">{error} <button onClick={() => {setError(''); setVersion(v => v + 1);}}>Повторить загрузку</button></p>}
    <form onSubmit={e => {e.preventDefault(); void action('/api/predictions/leagues', {name});}}>
      <label>Название лиги <input required minLength={2} maxLength={50} value={name} onChange={e => setName(e.target.value)} /></label>
      <button disabled={busy}>Создать лигу</button>
    </form>
    <details open={Boolean(token)}><summary>Вступить по приглашению</summary><p>Вступление откроет участникам ваше имя и очки, но не ответы.</p>
      <form onSubmit={e => {e.preventDefault(); void action('/api/predictions/leagues/join', {token});}}>
        <label>Код приглашения <input required minLength={40} maxLength={64} value={token} onChange={e => setToken(e.target.value.trim())} /></label>
        <button disabled={busy}>Вступить</button>
      </form>
    </details>
    {leagues.map(l => <article key={l.id}>
      <button onClick={() => {setScores(null); setRound(0); setSelected(l.id); setVersion(v => v + 1);}}>{l.name} →</button>
      {l.owner ? <details><summary>Приглашение (30 дней)</summary>
        <input aria-label="Ссылка приглашения" readOnly value={`${window.location.origin}/predictions?tab=leagues#invite=${l.invite_token}`} onFocus={e => e.target.select()} />
        <button disabled={busy} onClick={() => void action(`/api/predictions/leagues/${l.id}`, {action: 'rotate'})}>Заменить ссылку и отозвать старую</button>
      </details> : <button disabled={busy} onClick={() => void action(`/api/predictions/leagues/${l.id}`, {action: 'leave'})}>Покинуть лигу</button>}
      {selected === l.id && (scores ? <>
        <label>Зачёт <select value={round} onChange={e => setRound(Number(e.target.value))}><option value={0}>Сезон {scores.season}</option>{scores.rounds.map(r => <option key={r.round} value={r.round}>{r.event_name}</option>)}</select></label>
        {round ? <StageScores entries={scores.entries} round={round} /> : <ol className="league-score-list">{scores.entries.map((e, index) => <li key={e.user_id}>#{index + 1} {e.display_name} {e.place_change != null && <small>{e.place_change > 0 ? '↑' : e.place_change < 0 ? '↓' : '·'}{Math.abs(e.place_change)}</small>}<b>{e.total_points} очк.</b></li>)}</ol>}
      </> : <p role="status">Загружаем таблицу…</p>)}
    </article>)}
    {!leagues.length && <p>Пока нет лиг. Создайте свою или примите приглашение друга.</p>}
  </section>;
}
