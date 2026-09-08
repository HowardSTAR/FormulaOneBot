import { useEffect, useState } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import "./prediction-analytics.css";

type Event = { round: number; event_name: string; race_start_utc: string; quali_start_utc: string; is_cancelled?: boolean };
type Summary = { id: string; round: number; session: string; created_at: number; status: string; settled_at: number | null };
type Driver = { code: string; name: string; team: string; win: number; podium: number; top10: number; expected: number; range: number[]; dnf: number; reasons: string[] };
type Snapshot = Summary & { error: string | null; payload: null | {
  event: Event; cutoff: number; current_label: string; warnings: string[]; news_policy: string;
  model: { version: string; trials: number; drivers: Driver[]; scenarios: { label: string; probability: number; why: string; top5: string[] }[] };
  inputs: { history: { name: string; season: number; round: number }[];
    weather: { available: boolean; reason?: string; rain?: number; temperature?: number; wind?: number; hour?: string };
    news_available: boolean; news: { title: string; url: string; published_at: number }[] };
}; actual: null | { rows: { code: string; name: string; position: number }[]; metrics: { matched: number; total: number; mae: number | null; winner_brier: number | null } } };
type Index = { events: Event[]; snapshots: Summary[]; warning: string | null };
const base = "/api/admin/prediction-analytics";
const percent = (v: number) => `${(v * 100).toFixed(1)}%`;
const date = (v: number) => new Date(v * 1000).toLocaleString("ru-RU");
const sessionName = (v: string) => v === "race" ? "Гонка" : "Квалификация";

export default function PredictionAnalyticsPage() {
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

  useEffect(() => {
    let active = true;
    void apiRequest<Index>(base, { season }).then(data => {
      if (!active) return;
      setIndex(data);
      setRound(previous => data.events.some(e => e.round === previous) ? previous : (data.events.find(e => !e.is_cancelled && Date.parse(e.race_start_utc) > Date.now())?.round ?? data.events[0]?.round ?? 0));
    }).catch(e => { if (active) setError(String(e.message)); });
    return () => { active = false; };
  }, [season, revision]);

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

  const choose = (id: string) => { setSnapshot(null); setSelected(id); setSelectionRevision(v => v + 1); };
  const generate = async () => {
    setBusy(true); setError("");
    try {
      const result = await apiRequest<{ id: string }>(base, { season, round, session }, "POST");
      choose(result.id); setRevision(v => v + 1);
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось запустить расчёт"); }
    finally { setBusy(false); }
  };
  const event = index?.events.find(e => e.round === round);
  const starts = event && Date.parse(session === "race" ? event.race_start_utc : event.quali_start_utc);
  const canGenerate = !!starts && starts > Date.now() && !event?.is_cancelled;
  const p = snapshot?.payload;
  const isRace = snapshot?.session === "race";
  const actual = new Map(snapshot?.actual?.rows.map(r => [r.code, r.position]) ?? []);

  return <main className="pa-page">
    <BackButton />
    <header className="pa-hero">
      <div className="pa-eyebrow">TURBOTEARS / RESEARCH LAB <span>ADMIN ONLY</span></div>
      <h1>Аналитика<br /><em>предсказаний</em></h1>
      <p>Не один исход — пространство вероятностей. Форма, история трассы и условия уикенда в воспроизводимой модели.</p>
      <div className="pa-warning">Экспериментальная модель · пока не откалибрована на независимой выборке. Проценты приблизительные и не гарантируют результат.</div>
    </header>
    <section className="pa-controls" aria-label="Параметры прогноза">
      <label>Сезон<select value={season} onChange={e => { setSeason(Number(e.target.value)); setIndex(null); setSelected(""); setSnapshot(null); setRound(0); }}>{[0, 1, 2].map(offset => <option key={offset}>{new Date().getFullYear() - offset}</option>)}</select></label>
      <label>Этап<select value={round} onChange={e => setRound(Number(e.target.value))}><option value={0} disabled>Выберите этап</option>{index?.events.map(e => <option key={e.round} value={e.round} disabled={e.is_cancelled}>{e.round}. {e.event_name}</option>)}</select></label>
      <label>Сессия<select value={session} onChange={e => setSession(e.target.value)}><option value="race">Гонка</option><option value="qualifying">Квалификация</option></select></label>
      <button className="pa-primary" onClick={() => void generate()} disabled={!canGenerate || busy || snapshot?.status === "pending"}>{busy ? "Запускаем…" : "Рассчитать прогноз ↗"}</button>
      {!canGenerate && index && <small>Новые прогнозы доступны только до старта сессии. Старые расчёты остаются в истории.</small>}
    </section>
    {error && <p className="pa-warning" role="alert">{error}</p>}
    {index?.warning && <p role="status">{index.warning}</p>}
    {snapshot?.status === "pending" && <section className="pa-panel" role="status"><h2>Собираем данные и моделируем сессию…</h2><p>До трёх минут. Расчёт продолжится, даже если закрыть страницу; его можно открыть из истории.</p></section>}
    {snapshot?.error && <p className="pa-warning" role="alert">{snapshot.error}</p>}
    {p && snapshot && <>
      <section className="pa-heading"><div><div className="pa-eyebrow">{sessionName(snapshot.session)} · {date(p.cutoff)}</div><h2>{p.event.event_name}</h2></div><span className="pa-badge">{snapshot.actual ? "Результат зафиксирован" : "Прогноз сохранён"}</span></section>
      <div className="pa-stats">
        <article><strong>{p.model.trials.toLocaleString("ru-RU")}</strong><span>симуляций сессии</span></article>
        <article><strong>{p.inputs.history.length}</strong><span>исторических классификаций</span></article>
        <article><strong>{p.inputs.weather.available ? percent(p.inputs.weather.rain ?? 0) : "Нет данных"}</strong><span>осадки в час старта · Open-Meteo</span></article>
      </div>
      {p.warnings.map(w => <p className="pa-warning" key={w}>{w}</p>)}
      <h2>Три пути к {isRace ? "финишу" : "поулу"}</h2>
      <p className="pa-muted">Проценты относятся к группе победителя и в сумме дают 100%, а не к точному порядку пилотов.</p>
      <div className="pa-scenarios">{p.model.scenarios.map((s, i) => <article className="pa-panel" key={s.label}><div className="pa-scenario-top"><span>0{i + 1}</span><strong>{percent(s.probability)}</strong></div><h3>{s.label}</h3><p>{s.why}</p><ol>{s.top5.map(name => <li key={name}>{name}</li>)}</ol></article>)}</div>
      <section className="pa-panel"><h2>Вероятности по пилотам</h2><p className="pa-muted">Диапазон мест охватывает центральные 80% симуляций. {isRace ? "Риск схода включён." : "Топ-10 означает место 1–10, не гарантированное прохождение Q3."}</p>
        <div className="pa-table-wrap"><table><thead><tr><th>Пилот / команда</th><th>{isRace ? "Победа" : "Поул"}</th><th>Топ-3</th><th>Топ-10</th><th>Среднее / диапазон</th>{isRace && <th>Сход</th>}{snapshot.actual && <th>Факт</th>}</tr></thead><tbody>{p.model.drivers.map(d => <tr key={d.code}><td><details><summary>{d.name}<small>{d.team}</small></summary><ul>{d.reasons.map(r => <li key={r}>{r}</li>)}</ul></details></td><td><strong>{percent(d.win)}</strong><meter min="0" max="1" value={d.win} aria-label={`${d.name}: вероятность первого места`} /></td><td>{percent(d.podium)}</td><td>{percent(d.top10)}</td><td>{d.expected.toFixed(1)} <small>P{d.range[0]}–P{d.range[1]}</small></td>{isRace && <td>{percent(d.dnf)}</td>}{snapshot.actual && <td>{actual.has(d.code) ? `P${actual.get(d.code)}` : "Нет в результате"}</td>}</tr>)}</tbody></table></div>
      </section>
      {snapshot.actual && <section className="pa-panel"><h2>Прогноз / факт</h2><p>Результат сохранён {date(snapshot.settled_at!)}. Исходный прогноз не изменялся.</p><div className="pa-stats"><article><strong>{snapshot.actual.metrics.mae?.toFixed(2) ?? "—"}</strong><span>средняя ошибка позиции</span></article><article><strong>{snapshot.actual.metrics.winner_brier?.toFixed(4) ?? "—"}</strong><span>Brier первого места · меньше лучше</span></article><article><strong>{snapshot.actual.metrics.matched}/{snapshot.actual.metrics.total}</strong><span>пилотов сопоставлено</span></article></div></section>}
      <div className="pa-context"><section className="pa-panel"><h2>Условия и источники</h2><p>{p.current_label}</p><p>{p.inputs.weather.available ? `${p.inputs.weather.temperature} °C · ветер ${p.inputs.weather.wind} км/ч. Прогноз на ${p.inputs.weather.hour} UTC.` : `${p.inputs.weather.reason}. Использован повышенный разброс, а не выдуманный прогноз погоды.`}</p><a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Погода: Open-Meteo ↗</a><h3>История</h3><ul>{p.inputs.history.map(h => <li key={`${h.season}-${h.round}`}>{h.season} · {h.name}</li>)}</ul><a href="https://jolpi.ca/ergast/" target="_blank" rel="noreferrer">Классификации: Jolpica ↗</a></section>
        <section className="pa-panel"><h2>Новостной контекст</h2><p>{p.news_policy}</p>{!p.inputs.news.length && <p>{p.inputs.news_available ? "За последние 7 дней нет доступных публикаций." : "Новостной источник временно недоступен."}</p>}{p.inputs.news.map(n => <a className="pa-news" key={n.url} href={n.url} target="_blank" rel="noreferrer"><span>{n.title} ↗</span><small>BBC Sport · {date(n.published_at)}</small></a>)}</section></div>
      <details className="pa-panel"><summary>Как считается · {p.model.version}</summary><p>Рейтинг: 60% форма пилота, 30% команда, 10% история трассы. Вес прошлых сессий убывает в 0,85 раза; предыдущего сезона — дополнительно в 0,65 раза. Малые выборки сглаживаются двумя нейтральными наблюдениями.</p><p>Для гонки квалификация получает вес 30%, для квалификации последняя практика — 12%. Порядок моделируется случайными возмущениями Гумбеля; риск схода — бета-сглаженной частотой. Осадки увеличивают разброс и риск схода. Вероятность осадков в час старта используется как приближение, а не вероятность дождя на протяжении всей сессии.</p><p>Не учитываются автоматически штрафы, стратегия пит-стопов, топливо и индивидуальная форма на мокрой трассе. Это базовая исследовательская модель. Метрики появятся после публикации полной классификации, не раньше четырёх часов после старта.</p></details>
    </>}
    <section className="pa-panel"><h2>История расчётов</h2><p className="pa-muted">Каждый расчёт сохраняется отдельно. Старые прогнозы не пересчитываются по известному результату.</p>{!index ? <p role="status">Загрузка…</p> : !index.snapshots.length ? <p>Пока нет расчётов. Выберите будущую сессию и создайте первый прогноз.</p> : <div className="pa-history">{index.snapshots.map(s => <button key={s.id} aria-pressed={selected === s.id} onClick={() => choose(s.id)}><span>Этап {s.round} · {sessionName(s.session)}</span><small>{date(s.created_at)} · {s.settled_at ? "Прогноз + факт" : s.status === "ready" ? "Сохранён" : s.status === "pending" ? "Расчёт" : "Ошибка"}</small></button>)}</div>}</section>
  </main>;
}
