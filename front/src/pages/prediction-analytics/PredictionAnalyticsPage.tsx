import { SelectField } from '../../components/CustomSelect';
import { useEffect, useRef, useState } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import "./prediction-analytics.css";
import "./deep-history.css";
import { AllDrivers, ForecastScenarios } from './ForecastBreakdown';

type Event = { round: number; event_name: string; race_start_utc: string; quali_start_utc: string; is_cancelled?: boolean };
type Summary = { id: string; season: number; round: number; session: string; created_at: number; status: string; settled_at: number | null };
type Driver = { code: string; name: string; team: string; win: number; podium: number; top10: number; expected: number; range: number[]; dnf: number; reasons: string[];
  factors?: { key: string; label: string; value: number; weight: number; contribution: number; samples: number; effective_samples: number }[];
  timeline?: { season: number; round: number; name: string; position: number; dnf: boolean; team: string }[] };
type Snapshot = Summary & { error: string | null; payload: null | {
  event: Event; cutoff: number; current_label: string; warnings: string[]; news_policy: string;
  model: { version: string; trials: number; drivers: Driver[]; scenarios: { label: string; probability: number; why: string; top5: string[] }[] };
  inputs: { history: { name: string; season: number; round: number; session?: string }[];
    coverage?: { requested_years: number[]; loaded_years: number[]; races: number; qualifying: number; observations: number; unavailable: string[] };
    weather: { available: boolean; reason?: string; rain?: number; temperature?: number; wind?: number; hour?: string };
    news_available: boolean; news: { title: string; url: string; published_at: number }[] };
}; actual: null | { rows: { code: string; name: string; position: number }[]; metrics: { matched: number; total: number; mae: number | null; winner_brier: number | null } } };
type Index = { events: Event[]; snapshots: Summary[]; warning: string | null };
const base = "/api/admin/prediction-analytics";
const percent = (v: number) => `${(v * 100).toFixed(1)}%`;
const date = (v: number) => new Date(v * 1000).toLocaleString("ru-RU");
const sessionName = (v: string) => v === "race" ? "Гонка" : "Квалификация";

export default function PredictionAnalyticsPage() {
  const historyHeading = useRef<HTMLHeadingElement>(null);
  const historyButtons = useRef(new Map<string, HTMLButtonElement>());
  const [historySession, setHistorySession] = useState('all');
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const [deleting, setDeleting] = useState<Summary | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [notice, setNotice] = useState('');
  const [season, setSeason] = useState(new Date().getFullYear());
  const [index, setIndex] = useState<Index | null>(null);
  const [round, setRound] = useState(0);
  const [session, setSession] = useState("race");
  const [selected, setSelected] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [selectionRevision, setSelectionRevision] = useState(0);
  const [driverCode, setDriverCode] = useState("");

  useEffect(() => {
    let active = true;
    void apiRequest<Index>(base, { season }).then(data => {
      if (!active) return;
      setIndex(data);
      setSelected(previous => previous || data.snapshots.find(item => historySession === 'all' || item.session === historySession)?.id || '');
      setRound(previous => data.events.some(e => e.round === previous) ? previous : (data.events.find(e => !e.is_cancelled && Date.parse(e.race_start_utc) > Date.now())?.round ?? data.events[0]?.round ?? 0));
    }).catch(e => { if (active) setError(String(e.message)); });
    return () => { active = false; };
  }, [season, revision, historySession]);

  useEffect(() => {
    if (!selected) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await apiRequest<Snapshot>(`${base}/${selected}`);
        if (!active) return;
        setSnapshot(data);
        if (data.status === "pending") timer = setTimeout(() => void poll(), 3000);
        else setRevision(v => v + 1);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Не удалось загрузить прогноз"); }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [selected, selectionRevision]);

  const choose = (id: string) => { setError(""); setNotice(""); setSnapshot(null); setSelected(id); setSelectionRevision(v => v + 1); };
  const generate = async () => {
    setBusy(true); setError("");
    try {
      const result = await apiRequest<{ id: string }>(base, { season, round, session }, "POST");
      setHistorySession(session); choose(result.id); setRevision(v => v + 1);
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось запустить расчёт"); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true); setDeleteError('');
    try {
      await apiRequest(`${base}/${encodeURIComponent(deleting.id)}`, {}, 'DELETE');
      setIndex(value => value ? {...value, snapshots: value.snapshots.filter(item => item.id !== deleting.id)} : value);
      const remaining = index?.snapshots.filter(item => item.id !== deleting.id) ?? [];
      const next = remaining.find(item => historySession === 'all' || item.session === historySession);
      if (selected === deleting.id) { choose(next?.id ?? ''); }
      deleteDialog.current?.close();
      if (next) historyButtons.current.get(next.id)?.focus();
      else historyHeading.current?.focus();
      setNotice('Расчёт удалён из истории.');
      setDeleting(null);
    } catch (e) { setDeleteError(e instanceof Error ? e.message : 'Не удалось удалить расчёт. Попробуйте снова.'); }
    finally { setDeleteBusy(false); }
  };
  const event = index?.events.find(e => e.round === round);
  const starts = event && Date.parse(session === "race" ? event.race_start_utc : event.quali_start_utc);
  const canGenerate = !!starts && starts > Date.now() && !event?.is_cancelled;
  const p = snapshot?.payload;
  const focusDriver = p?.model.drivers.find(d => d.code === driverCode) ?? p?.model.drivers[0];
  const isRace = snapshot?.session === "race";
  const actual = new Map(snapshot?.actual?.rows.map(r => [r.code, r.position]) ?? []);
  const leaders = [...(p?.model.drivers ?? [])].sort((a,b) => b.win-a.win);
  const winner = snapshot?.actual?.rows.find(row => row.position === 1);
  const filteredHistory = index?.snapshots.filter(item => historySession === 'all' || item.session === historySession) ?? [];
  return <main className="pa-page">
    <BackButton />
    <header className="pa-hero">

      <h1>Аналитика предсказаний</h1>
      <p>Не один исход — пространство вероятностей. Форма, история трассы и условия уикенда в воспроизводимой модели.</p>

    </header>
    <details className="pa-new" open={!selected}><summary>Новый расчёт</summary><h2 className="pa-sr-only">Параметры</h2><p className="ui-data-context">Эти параметры относятся к новому расчёту, а не к открытому сохранённому прогнозу ниже.</p>
    <section className="pa-controls" aria-label="Параметры нового расчёта">
      <span className="pa-new-season">Сезон {season}</span>
      <label>Этап<SelectField value={round} onChange={e => setRound(Number(e))}><option value={0} disabled>Выберите этап</option>{index?.events.map(e => <option key={e.round} value={e.round} disabled={e.is_cancelled}>{e.round}. {e.event_name}</option>)}</SelectField></label>
      <label>Сессия<SelectField value={session} onChange={e => setSession(e)}><option value="race">Гонка</option><option value="qualifying">Квалификация</option></SelectField></label>
      <button className="pa-primary" onClick={() => void generate()} disabled={!canGenerate || busy || snapshot?.status === "pending"}>{busy ? "Запускаем…" : "Рассчитать прогноз ↗"}</button>
      {!canGenerate && index && <small>Новые прогнозы доступны только до старта сессии. Старые расчёты остаются в истории.</small>}
    </section>
    </details>
    <div className="pa-workspace">
    <aside className="pa-library" aria-labelledby="pa-library-title"><div className="pa-library-title"><h2 id="pa-library-title" ref={historyHeading} tabIndex={-1}>Мои расчёты</h2><span>{index?.snapshots.length ?? '—'}</span></div>
      <div className="pa-library-filters"><label>Сезон<SelectField value={season} onChange={value => {setSeason(Number(value));setIndex(null);setSelected('');setSnapshot(null);setRound(0);setError('');}}>{[0,1,2].map(offset => <option key={offset}>{new Date().getFullYear()-offset}</option>)}</SelectField></label><label>Сессия<SelectField value={historySession} onChange={value => {setHistorySession(value); const next = index?.snapshots.find(item => value === 'all' || item.session === value); if(next && !index?.snapshots.some(item => item.id === selected && (value === 'all' || item.session === value))) choose(next.id);}}><option value="all">Все сессии</option><option value="race">Гонки</option><option value="qualifying">Квалификации</option></SelectField></label></div>{!index ? <p role="status">Загрузка…</p> : !index.snapshots.length ? <p>Пока нет расчётов. Выберите будущую сессию и создайте первый прогноз.</p> : !filteredHistory.length ? <p className="pa-muted">В этой сессии ещё нет расчётов.</p> : <div className="pa-history">{filteredHistory.map(s => <div className="pa-history-row" key={s.id}>
      <button ref={node => {if(node) historyButtons.current.set(s.id,node);else historyButtons.current.delete(s.id);}} className="pa-history-open" aria-pressed={selected === s.id} onClick={() => choose(s.id)}><span>{index.events.find(event => event.round === s.round)?.event_name || `Этап ${s.round}`}</span><small>{s.season} · этап {s.round} · {sessionName(s.session)} · {date(s.created_at)}</small><small>{s.settled_at ? 'Прогноз + факт' : s.status === 'ready' ? 'Сохранён' : s.status === 'pending' ? 'Расчёт…' : 'Ошибка'}</small></button>
      <button className="pa-delete" disabled={s.status === 'pending'} aria-label={`Удалить расчёт: ${s.season}, этап ${s.round}, ${date(s.created_at)}`} title={s.status === 'pending' ? 'Дождитесь завершения расчёта' : 'Удалить расчёт'} onClick={() => {setDeleting(s);setDeleteError('');deleteDialog.current?.showModal();}}><svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" /></svg></button>
    </div>)}</div>}</aside>
    <div className="pa-reading">
    <p className="pa-notice" role="status">{notice}</p>
    {selected && !snapshot && !error && <p role="status">Загружаем сохранённый расчёт…</p>}
    {error && <div className="pa-warning" role="alert"><p>{error}</p><button onClick={() => {setError('');setRevision(v=>v+1);setSelectionRevision(v=>v+1);}}>Повторить загрузку</button></div>}
    {index?.warning && <p role="status">{index.warning}</p>}
    {snapshot?.status === "pending" && <section className="pa-panel" role="status"><h2>Собираем данные и моделируем сессию…</h2><p>Обычно до трёх минут. При временном сбое расчёт повторится автоматически; страницу можно закрыть. После начала сессии новый прогноз не создаётся.</p></section>}
    {snapshot?.error && <p className="pa-warning" role="alert">{snapshot.error}</p>}
    {!selected && index && <div className="pa-empty"><h2>Здесь будет ваш отчёт</h2><p>Откройте сохранённый расчёт или выберите будущий этап в «Новом расчёте».</p></div>}
    {p && snapshot && <article className="pa-report" aria-label="Отчёт о прогнозе">
      <div className="pa-report-signature"><strong>Turbo<span>Tears</span></strong><span>Прогноз · {p.model.version}</span></div>
      <section className="pa-heading"><div><div className="pa-eyebrow"> {snapshot.season} · этап {snapshot.round} · {sessionName(snapshot.session)} · {date(p.cutoff)}</div><h2>{p.event.event_name}</h2></div><span className="pa-badge">{snapshot.actual ? "Результат зафиксирован" : "Прогноз сохранён · факт ещё не получен"}</span></section>
      <div className="pa-verdict">
        <h3>{snapshot.actual ? 'Что получилось' : 'Коротко о прогнозе'}</h3>
        {leaders[0] ? <p>Лидер модели — <strong>{leaders[0].name}</strong>. Вероятность {isRace ? 'победы' : 'поула'}: <strong>{percent(leaders[0].win)}</strong>.{leaders[1] && <> Далее — {leaders[1].name}: {percent(leaders[1].win)}. Разница — {((leaders[0].win-leaders[1].win)*100).toLocaleString('ru-RU',{maximumFractionDigits:1})} п. п.</>}{winner && <> {isRace ? 'Гонку выиграл' : 'Поул занял'} <strong>{winner.name}</strong>.</>}</p> : <p>Нет данных о вероятностях пилотов.</p>}
        <p className="pa-disclosure">Экспериментальная модель. Вероятности приблизительные, точность на независимой выборке пока не подтверждена.</p>
      </div>
      {snapshot.actual && <section className="pa-outcome" aria-labelledby="pa-outcome-title"><h2 id="pa-outcome-title">Прогноз и результат</h2><p className="pa-muted">Пять лучших средних позиций модели. Среднее место — результат симуляций, а не точный порядок финиша.</p><table className="pa-comparison"><caption className="pa-sr-only">Среднее ожидаемое место и фактический финиш</caption><thead><tr><th scope="col">Пилот</th><th scope="col">Ожидалось</th><th scope="col">Факт</th></tr></thead><tbody>{[...p.model.drivers].sort((a,b)=>a.expected-b.expected).slice(0,5).map(d=><tr key={d.code}><th scope="row">{d.name}</th><td><small aria-hidden="true">Ожидалось</small>{d.expected.toLocaleString('ru-RU',{maximumFractionDigits:1})}</td><td><small aria-hidden="true">Факт</small>{actual.has(d.code) ? `P${actual.get(d.code)}` : 'Нет данных'}</td></tr>)}</tbody></table></section>}
      <section className="pa-leaders" aria-labelledby="pa-leaders-title">
        <div className="pa-section-title"><h2 id="pa-leaders-title">{snapshot.actual ? 'Вероятности до старта' : isRace ? 'Претенденты на победу' : 'Претенденты на поул'}</h2><span>Вероятность по модели</span></div>
        <ol>{leaders.slice(0,5).map(d => <li key={d.code}>
          <div className="pa-leader-line"><div><strong>{d.name}</strong><small>{d.team}</small></div><b>{percent(d.win)}</b></div>
          <div className="pa-probability" aria-hidden="true"><span style={{width: `${Math.min(100, Math.max(0, d.win*100))}%`}} /></div>
          <div className="pa-leader-detail"><span>Топ-3 <strong>{percent(d.podium)}</strong></span><span>Среднее место <strong>{d.expected.toFixed(1)}</strong></span>{actual.has(d.code) && <span>Факт <strong>P{actual.get(d.code)}</strong></span>}</div>
        </li>)}</ol>

      </section>
      {p.warnings.map(w => <p className="pa-warning" key={w}>{w}</p>)}
      <AllDrivers key={`drivers-${snapshot.id}`} drivers={p.model.drivers} isRace={isRace} actual={actual} settled={!!snapshot.actual} />
      <ForecastScenarios scenarios={p.model.scenarios} drivers={p.model.drivers} isRace={isRace} />

      {snapshot.actual && <details className="pa-fold"><summary>Точность модели</summary><p>Результат сохранён {date(snapshot.settled_at!)}. Исходный прогноз не изменялся.</p><div className="pa-stats"><article><strong>{snapshot.actual.metrics.mae?.toFixed(2) ?? "—"}</strong><span>средняя ошибка позиции</span></article><article><strong>{snapshot.actual.metrics.winner_brier?.toFixed(4) ?? "—"}</strong><span>Brier первого места · меньше лучше</span></article><article><strong>{snapshot.actual.metrics.matched}/{snapshot.actual.metrics.total}</strong><span>пилотов сопоставлено</span></article></div></details>}
      <details className="pa-research pa-fold"><summary>Источники и методика</summary>      <div className="pa-stats">
        <article><strong>{p.model.trials.toLocaleString("ru-RU")}</strong><span>симуляций сессии</span></article>
        <article><strong>{p.inputs.history.length}</strong><span>исторических классификаций</span></article>
        <article><strong>{p.inputs.weather.available ? percent(p.inputs.weather.rain ?? 0) : "Нет данных"}</strong><span>осадки в час старта · Open-Meteo</span></article>
      </div>
      {p.inputs.coverage && <section className="pa-panel"><h2>Глубина истории</h2><p>Запрошены сезоны {p.inputs.coverage.requested_years.join(" · ")}. Загружены: {p.inputs.coverage.loaded_years.join(" · ")}.</p><div className="pa-stats"><article><strong>{p.inputs.coverage.races}</strong><span>гонок</span></article><article><strong>{p.inputs.coverage.qualifying}</strong><span>квалификаций</span></article><article><strong>{p.inputs.coverage.observations.toLocaleString("ru-RU")}</strong><span>результатов пилотов</span></article></div><p>Последние 6 выступлений — только свежая форма. Вся остальная история участвует в отдельных факторах с понижением веса за давность и смену команды.</p>{p.inputs.coverage.unavailable.length > 0 && <details><summary>Пробелы в данных ({p.inputs.coverage.unavailable.length})</summary><ul>{p.inputs.coverage.unavailable.map(s => <li key={s}>{s}</li>)}</ul></details>}</section>}
      {focusDriver?.factors && <section className="pa-panel"><h2>Почему модель так думает</h2><label className="pa-driver-select">Пилот <SelectField value={focusDriver.code} onChange={e => setDriverCode(e)}>{p.model.drivers.map(d => <option key={d.code} value={d.code}>{d.name}</option>)}</SelectField></label><p className="pa-muted">Вклад — изменение рейтинга относительно нейтральной оценки 0,5, не прибавка к вероятности победы. Ноль наблюдений означает отсутствие данных, а не плохой результат.</p><div className="pa-factors">{focusDriver.factors.map(f => <article key={f.key}><div><strong>{f.label}</strong><span className={f.contribution >= 0 ? "pa-positive" : "pa-negative"}>{f.contribution >= 0 ? "+" : ""}{(100 * f.contribution).toFixed(1)} п. рейтинга</span></div><meter min="0" max="1" value={f.value} aria-label={f.label} /><small>Оценка {f.value.toFixed(2)} · вес {percent(f.weight)} · {f.samples} наблюдений / {f.effective_samples.toFixed(1)} взвешенных</small></article>)}</div><h3>Последние выступления</h3><div className="pa-timeline">{focusDriver.timeline?.map(t => <div key={`${t.season}-${t.round}`} title={`${t.name}, ${t.team}`}><strong>{t.dnf ? "Сход" : `P${t.position}`}</strong><small>{t.season} · этап {t.round}</small><span>{t.name}</span></div>)}</div></section>}
      <div className="pa-context"><section className="pa-panel"><h2>Условия и источники</h2><p>{p.current_label}</p><p>{p.inputs.weather.available ? `${p.inputs.weather.temperature} °C · ветер ${p.inputs.weather.wind} км/ч. Прогноз на ${p.inputs.weather.hour} UTC.` : `${p.inputs.weather.reason}. Использован повышенный разброс, а не выдуманный прогноз погоды.`}</p><a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Погода: Open-Meteo ↗</a><details><summary>История: все {p.inputs.history.length} сессий</summary><ul className="pa-archive">{p.inputs.history.map(h => <li key={`${h.season}-${h.round}-${h.session}`}>{h.season} · {h.name} · {h.session ? sessionName(h.session) : "сессия"}</li>)}</ul></details><a href="https://jolpi.ca/ergast/" target="_blank" rel="noreferrer">Классификации: Jolpica ↗</a></section>
        <section className="pa-panel"><h2>Новостной контекст</h2><p>{p.news_policy}</p>{!p.inputs.news.length && <p>{p.inputs.news_available ? "За последние 7 дней нет доступных публикаций." : "Новостной источник временно недоступен."}</p>}{p.inputs.news.map(n => <a className="pa-news" key={n.url} href={n.url} target="_blank" rel="noreferrer"><span>{n.title} ↗</span><small>BBC Sport · {date(n.published_at)}</small></a>)}</section></div>
      <details className="pa-method"><summary>Как считается · {p.model.version}</summary>{p.inputs.coverage ? <p>Пять сезонов, отдельные факторы долгосрочной и свежей формы, команды, трассы, квалификаций, напарника и отыгрыша позиций. Вес истории уменьшается вдвое за 540 дней, выступления за другую команду получают множитель 0,55, до границы регламента 2026 — 0,4. Все коэффициенты пока эвристические, не обученные. Стабильность результатов влияет на разброс; риск схода учитывает пилота и текущую команду.</p> : <p>Архивная модель v1: 60% форма пилота, 30% команда, 10% история трассы; до 6 последних сессий и прошлый этап на этой трассе.</p>}<p>Для гонки квалификация получает вес 30%, для квалификации последняя практика — 12%. Порядок моделируется случайными возмущениями Гумбеля; риск схода — бета-сглаженной частотой. Осадки увеличивают разброс и риск схода. Вероятность осадков в час старта используется как приближение, а не вероятность дождя на протяжении всей сессии.</p><p>Не учитываются автоматически штрафы, стратегия пит-стопов, топливо и индивидуальная форма на мокрой трассе. Это исследовательская модель, точность ещё не подтверждена независимой проверкой. Метрики появятся после публикации полной классификации, не раньше четырёх часов после старта.</p></details>
      </details>
      <footer className="pa-report-footer"><span>TurboTears · {snapshot.season} · этап {snapshot.round}</span><span>Расчёт от {date(p.cutoff)}</span></footer>
    </article>}
    </div></div>
    <dialog className="pa-delete-dialog" ref={deleteDialog} aria-labelledby="pa-delete-title" onCancel={e => {if (deleteBusy) e.preventDefault();}} onClose={() => {setDeleting(null);setDeleteError('');}}>
      <h2 id="pa-delete-title">Удалить сохранённый расчёт?</h2>
      <p>{deleting && `${deleting.season} · этап ${deleting.round} · ${sessionName(deleting.session)} · ${date(deleting.created_at)}`}</p>
      <p>Прогноз и сравнение с результатом будут удалены без возможности восстановления. Другие расчёты сохранятся.</p>
      {deleteError && <p role="alert">{deleteError}</p>}
      <div><button disabled={deleteBusy} onClick={() => deleteDialog.current?.close()}>Отмена</button><button className="pa-confirm-delete" disabled={deleteBusy} onClick={() => void remove()}>{deleteBusy ? 'Удаляем…' : 'Удалить расчёт'}</button></div>
    </dialog>
  </main>;
}
