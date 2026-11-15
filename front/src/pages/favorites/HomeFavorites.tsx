import { useEffect, useState } from 'react';
import { Link, useBlocker } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
export type Favorites = { drivers: string[]; teams: string[] };
export function HomeFavorites({ favorites, initial, names, busy, onSaved, onDirty }: { favorites: Favorites; initial?: Favorites; names: Record<string, string>; busy: boolean; onSaved: (value: Favorites) => void; onDirty: (dirty: boolean) => void }) {
  const available = (kind: keyof Favorites, limit: number) => {
    const selected = (initial?.[kind] || []).filter(value => favorites[kind].includes(value));
    return [...selected, ...favorites[kind].filter(value => !selected.includes(value))].slice(0, limit);
  };
  const [draft, setDraft] = useState<Favorites>(() => ({ drivers: available('drivers', 2), teams: available('teams', 1) }));
  const [saved, setSaved] = useState(() => JSON.stringify(draft));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const dirty = saved !== JSON.stringify(draft);
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    if (window.confirm('Выбор для главной не сохранён. Уйти и потерять изменения?')) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const save = async () => {
    setSaving(true); setError('');
    try {
      await apiRequest('/api/favorites/home', draft, 'POST');
      setSaved(JSON.stringify(draft)); onSaved(draft);
    } catch { setError('Не удалось сохранить выбор для главной. Попробуйте ещё раз.'); }
    finally { setSaving(false); }
  };
  const selectDriver = (index: number, value: string) => {
    setDraft(current => {
      const drivers = [...current.drivers];
      const previous = drivers.indexOf(value);
      if (previous >= 0) drivers[previous] = drivers[index];
      drivers[index] = value;
      return { ...current, drivers };
    });
  };
  return <section className="favorites-home" aria-labelledby="favorites-home-title">
    <h2 id="favorites-home-title">Кто на главной</h2>
    <p>Два пилота и одна команда из избранного: их очки и места будут на главной и на компьютере, и на телефоне.</p>
    {!favorites.drivers.length && !favorites.teams.length ? <p>Добавьте избранных ниже — затем здесь можно выбрать, кого показывать.</p> : <>
      <div className="favorites-home-fields">
        {[0, 1].map(index => <label key={index}>Пилот {index + 1}
          <select aria-label={`Пилот ${index + 1}`} value={draft.drivers[index] || ''} disabled={busy || saving || !draft.drivers[index]} onChange={event => selectDriver(index, event.target.value)}>
            {!draft.drivers[index] && <option value="">Добавьте пилота в избранное</option>}
            {favorites.drivers.map(code => <option key={code} value={code}>{names[code] || code}</option>)}
          </select>
        </label>)}
        <label>Команда<select aria-label="Команда" value={draft.teams[0] || ''} disabled={busy || saving || !draft.teams.length} onChange={event => setDraft(current => ({ ...current, teams: [event.target.value] }))}>
          {!draft.teams.length && <option value="">Добавьте команду в избранное</option>}
          {favorites.teams.map(team => <option key={team} value={team}>{team}</option>)}
        </select></label>
      </div>
      <div className="favorites-home-actions"><button type="button" disabled={busy || saving || !dirty} onClick={() => void save()}>{saving ? 'Сохранение…' : 'Сохранить выбор для главной'}</button><Link to="/">На главную →</Link></div>
      <p role="status">{saving ? 'Сохраняем выбор…' : dirty ? 'Есть несохранённые изменения для главной.' : 'Выбор для главной сохранён.'}</p>
      {error && <p role="alert">{error}</p>}
    </>}
  </section>;
}
