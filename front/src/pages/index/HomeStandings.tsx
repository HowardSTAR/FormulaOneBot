import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { optionalNumber } from '../../helpers/presentation';
import { GlassSwitch } from './GlassSwitch';

type Standing = { position: number; name: string; points: number; constructorName?: string };
type StandingsState = { season: number; round?: number; rows: Standing[]; failed: boolean };
type Category = 'drivers' | 'teams';

export function HomeStandings({ season }: { season: number }) {
  const [params] = useSearchParams();
  const category: Category = params.get('standing') === 'teams' ? 'teams' : 'drivers';
  const [data, setData] = useState<Partial<Record<Category, StandingsState>>>({});
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    async function get(kind: Category) {
      const key = kind === 'drivers' ? 'drivers' : 'constructors';
      try {
        const result = await apiRequest<{ drivers?: Standing[]; constructors?: Standing[]; round?: number }>(`/api/${key}`, { season });
        if (active) setData(previous => ({ ...previous, [kind]: { season, round: result.round, rows: (result[key] || []).slice(0, 5), failed: false } }));
      } catch {
        if (active) setData(previous => ({ ...previous, [kind]: { season, rows: [], failed: true } }));
      }
    }
    void get('drivers');
    void get('teams');
    return () => { active = false; };
  }, [season, refresh]);

  const state = data[category]?.season === season ? data[category] : undefined;
  const drivers = category === 'drivers';
  const fullPath = `${drivers ? '/drivers' : '/constructors'}?year=${season}`;
  const leaderPoints = optionalNumber(state?.rows.find(row => Number(row.position) === 1)?.points);
  const retry = () => { setData({}); setRefresh(value => value + 1); };
  const categoryPath = (value: Category) => {
    const next = new URLSearchParams(params);
    if (value === 'drivers') next.delete('standing'); else next.set('standing', value);
    return `/${next.size ? `?${next}` : ''}`;
  };

  return <section className="home-championship" aria-labelledby="home-championship-title">
    <header className="home-championship-head">
      <div><h2 id="home-championship-title">Чемпионат {season}</h2><p>Пять лидеров{state?.round ? ` после этапа ${state.round}` : ''}</p></div>
      <Link className="home-full-standing" to={fullPath}>Полный зачёт <span aria-hidden="true">↗</span></Link>
    </header>
    <GlassSwitch className="home-standing-switch" label="Выбрать зачёт" selected={category} items={[
      { id: 'drivers', label: 'Пилоты', to: categoryPath('drivers') },
      { id: 'teams', label: 'Команды', to: categoryPath('teams') },
    ]} />
    {!state ? <p className="home-empty" role="status">Загружаем {drivers ? 'личный зачёт' : 'кубок конструкторов'}…</p>
      : state.failed ? <div className="home-empty" role="status"><p>Не удалось загрузить {drivers ? 'очки пилотов' : 'очки команд'}.</p><button type="button" className="home-text-action" onClick={retry}>Повторить загрузку зачёта</button></div>
      : !state.rows.length ? <div className="home-empty"><p>Результаты сезона ещё не опубликованы.</p><Link to={fullPath} className="home-text-action">Открыть полный зачёт</Link></div>
      : <table className="home-standing-table">
        <caption className="home-sr-only">{drivers ? 'Личный зачёт' : 'Кубок конструкторов'}, сезон {season}, первые пять мест. Разница в очках относительно лидера.</caption>
        <thead><tr><th scope="col"><span className="home-sr-only">Место</span><span aria-hidden="true">№</span></th><th scope="col">{drivers ? 'Пилот' : 'Команда'}</th><th scope="col">Очки</th><th scope="col">От лидера</th></tr></thead>
        <tbody>{state.rows.map(row => {
          const points = optionalNumber(row.points);
          const gap = points !== null && leaderPoints !== null && leaderPoints >= points ? leaderPoints - points : null;
          return <tr key={`${row.position}-${row.name}`}>
            <td className="home-position">{row.position}</td>
            <th scope="row"><span className="home-entrant"><strong>{row.name}</strong>{drivers && row.constructorName && <small>{row.constructorName}</small>}</span></th>
            <td className="home-points">{points?.toLocaleString('ru-RU') ?? '—'}</td>
            <td className="home-gap">{gap === null ? '—' : gap === 0 ? Number(row.position) === 1 ? 'Лидер' : '0' : `−${gap.toLocaleString('ru-RU')}`}</td>
          </tr>;
        })}</tbody>
      </table>}
    <p className="home-standing-note">{drivers ? 'Личный зачёт пилотов' : 'Кубок конструкторов'} · очки за сезон</p>
  </section>;
}
