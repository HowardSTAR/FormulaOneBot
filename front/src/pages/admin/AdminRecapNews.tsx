import { SelectField } from '../../components/CustomSelect';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { apiRequest } from '../../helpers/api';
import './admin-tools.css';

type Source = {id: string; publisher: string; url: string; terms_url: string; permission_note: string; kind: string; permission_required: boolean; enabled: boolean; checked: number | null; successful: number | null; next_check: number; error: string | null};
type Article = {id: number; season: number; round: number; event_name: string; source_id: string; title: string; url: string; published: number; hidden: boolean};
type Visibility = 'all' | 'visible' | 'hidden';
type News = { sources: Source[]; items: Article[]; stages?: { round: number; event_name: string }[]; selected_round?: number | null };
const views: [Visibility, string][] = [['all', 'Все'], ['visible', 'В отборе'], ['hidden', 'Скрытые']];
const base = '/api/admin/tools/recap-news';
const date = (value: number | null) => value ? new Date(value * 1000).toLocaleString('ru-RU') : 'ещё не было';
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить запрос';

export function AdminRecapNews() {
  const [season, setSeason] = useState(String(new Date().getFullYear()));
  const [round, setRound] = useState('latest');
  const [visibility, setVisibility] = useState<Visibility>('all');
  const [data, setData] = useState<News | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [permission, setPermission] = useState<Record<string, boolean>>({});
  const query = useRef({ season: new Date().getFullYear(), latest: true, round_num: undefined as number | undefined, visibility: 'all' as Visibility });
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    try {
      const result = await apiRequest<News>(base, query.current);
      if (current === generation.current) setData(result);
    } catch (reason) {
      if (current === generation.current) setError(message(reason));
    }
  }, []);
  const cancelLoad = useCallback(() => { generation.current++; }, []);
  useEffect(() => { void load(); return cancelLoad; }, [load, cancelLoad]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  };
  const search = (event: FormEvent) => {
    event.preventDefault();
    query.current = { season: Number(season), round_num: round !== 'all' && round !== 'latest' ? Number(round) : undefined, latest: round === 'latest', visibility };
    void run(load);
  };
  const toggleSource = (source: Source) => void run(async () => {
    await apiRequest(`${base}/sources/${source.id}`, {enabled: !source.enabled, permission_confirmed: !!permission[source.id]}, 'PATCH');
    setPermission(previous => ({...previous, [source.id]: false}));
    setNotice(source.enabled ? 'Источник отключён. Его публикации скрыты, архив сохранён.' : 'Источник подключён. Фоновая проверка — в течение 15 минут после гонки.');
    await load();
  });
  const toggleArticle = (article: Article) => void run(async () => {
    await apiRequest(`${base}/articles/${article.id}`, {hidden: !article.hidden}, 'PATCH');
    setNotice(article.hidden ? 'Публикация возвращена в отбор.' : 'Публикация скрыта из новых ответов рекапа. Уже отправленные сообщения Telegram не изменяются.');
    await load();
  });
  return <section className="admin-chart-card admin-tools">

    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!data && !error && <p role="status">Загружаем источники и публикации…</p>}
    <fieldset disabled={busy}>
      <details className="recap-source-settings"><summary>Источники{data?.sources.some(source => source.error && source.enabled) ? ` · со сбоями: ${data.sources.filter(source => source.error && source.enabled).length}` : ''}</summary>
        <p>Autosport.com.ru и послегоночный журнал OpenF1 подключены по умолчанию. BBC требует отдельной проверки права использования. Отключение скрывает записи источника, не удаляя архив.</p>
        <div className="at-history">{data?.sources.map(source => <article key={source.id}>
          <h3>{source.publisher}{source.error && source.enabled && <span className="admin-status-warning"> · сбой загрузки</span>}</h3>
          <p>{source.permission_note} <a href={source.terms_url} target="_blank" rel="noopener noreferrer">Условия источника ↗</a></p>
          <p>{source.enabled ? 'Подключён' : 'Выключен'} · Проверка: {date(source.checked)} · Успешная загрузка: {date(source.successful)}</p>
          {source.error && <p role="status">{source.error}. Сохранённые новости не удаляются. Автоматический повтор не раньше: {date(source.next_check)}.</p>}
          {!source.enabled && source.permission_required && <label className="at-check"><input type="checkbox" checked={!!permission[source.id]} onChange={event => setPermission(previous => ({...previous, [source.id]: event.target.checked}))} />Подтверждаю право использования этой ленты для F1Hub</label>}
          <button type="button" disabled={!source.enabled && source.permission_required && !permission[source.id]} onClick={() => toggleSource(source)}>{source.enabled ? 'Отключить источник' : 'Подключить источник'}</button>
        </article>)}</div>
      </details>
      <form onSubmit={search} className="recap-news-filter">
        <label>Сезон<input required type="number" min="1950" max={new Date().getFullYear()} value={season} onChange={event => { setSeason(event.target.value); setRound('latest'); }} /></label>
        <label>Этап<SelectField value={round} onChange={setRound}>
          <option value="latest">Последний с публикациями</option><option value="all">Все этапы</option>
          {Number(season) === query.current.season && data?.stages?.map(stage => <option key={stage.round} value={stage.round}>Этап {stage.round} · {stage.event_name}</option>)}
        </SelectField></label>
        <button type="submit">Показать публикации</button>
      </form>
      <nav className="admin-inline-actions admin-subnav" aria-label="Видимость публикаций">{views.map(([value, label]) => <button type="button" key={value} aria-pressed={visibility === value} onClick={() => {
        setVisibility(value);
        query.current = { ...query.current, visibility: value };
        void run(load);
      }}>{label}</button>)}</nav>
      {data && !busy && !error && <p role="status">{query.current.season}{data.selected_round ? `, этап ${data.selected_round}` : ', все этапы'} · показано {data.items.length} публикаций из последних 200 по фильтру.</p>}
      {data && !busy && !error && !data.items.length && <p>В выбранном разделе публикаций нет.</p>}
      <div className="at-history">{!busy && !error && data?.items.map(article => <article key={article.id}>
        <small>{article.season} · этап {article.round} · {article.event_name} · {date(article.published)}</small>
        <h3>{article.source_id === 'openf1-control' ? article.title : <a href={article.url} target="_blank" rel="noopener noreferrer">{article.title} ↗</a>}</h3>
        <p>{data.sources.find(source => source.id === article.source_id)?.publisher || article.source_id} · {article.hidden ? 'Скрыта администратором' : data.sources.find(source => source.id === article.source_id)?.enabled ? article.source_id === 'openf1-control' ? 'Участвует в отборе ключевых событий' : 'Участвует в отборе трёх новостей' : 'Скрыта: источник выключен'}</p>
        <button type="button" onClick={() => toggleArticle(article)}>{article.hidden ? 'Вернуть в отбор' : 'Скрыть публикацию'}</button>
      </article>)}</div>
      <button type="button" className="recap-news-reload" onClick={() => void run(load)}>Обновить статусы и список</button>
    </fieldset>
  </section>;
}
