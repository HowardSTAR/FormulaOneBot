import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../../helpers/api";
import "./personal-review.css";
import { ShareButton } from '../../components/ShareButton';
import { confirmedFactsNote, localDateTime, optionalNumber, resultStatus } from '../../helpers/presentation';

type Item = { key: string; label: string; predicted: string | number | null; actual: string | number | string[] | null;
  position: number | null; points: number | null; maximum: number; status: string; reason: string;
  rule: { exact: number; offsets: number[] } };
type RaceFacts = { source: string; note?: string; fastest_lap?: {driver: string; lap: number; seconds: number};
  first_retirement_drivers?: string[]; retirement_order_method?: string;
  laps?: {driver: string; lap: number; seconds: number}[];
  retirements?: {driver: string; status: string; laps: number | null; time: string | null}[];
  retirement_order_confirmed?: boolean; safety_car?: number | null;
  safety_events?: {type: string; time: string; status: string}[] };
type Review = { event_name: string; points: number | null; max_points: number | null; complete: boolean; items: Item[]; race_facts?: RaceFacts | null };
function lapTime(seconds: number) {
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}
const statuses: Record<string,string> = { exact: "Угадано", partial: "Частичное попадание", miss: "Не угадано", unavailable: "Нет данных", unknown: "Не подтверждено" };
function value(key: string, v: string | number | string[] | null, names: Record<string, string>): string {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.map(code => value(key, code, names)).join(" · ");
  if (key === "safety_car") return Number(v) ? "Да" : "Нет";
  const code = String(v);
  return names[code.toUpperCase()] ? `${names[code.toUpperCase()]} (${code})` : code;
}

export function PersonalReview({ season, round, onClose }: { season: number; round: number; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [result, setResult] = useState<{ data?: Review; error?: string }>({});
  const [driverNames, setDriverNames] = useState<Record<string, string>>({});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    element?.showModal();
    let active = true;
    setResult({});
    apiRequest<Review>(`/api/predictions/mine/${season}/${round}`).then(data => { if (active) setResult({ data }); })
      .catch(error => { if (active) setResult({ error: error instanceof Error ? error.message : "Не удалось загрузить прогноз" }); });
    apiRequest<{drivers?: {code: string; name: string}[]}>('/api/drivers', {season})
      .then(data => { if (active) setDriverNames(Object.fromEntries((data.drivers || []).filter(driver => driver.code && driver.name).map(driver => [driver.code.toUpperCase(), driver.name.trim()]))); })
      .catch(() => { if (active) setDriverNames({}); });
    return () => { active = false; element?.close(); previous?.focus(); };
  }, [season, round, attempt]);
  return <dialog ref={dialog} className="personal-review" aria-labelledby="personal-review-title" onCancel={onClose}>
    <header><div><small>Только для вас · {season} · этап {round}</small><h2 id="personal-review-title">Мой прогноз</h2></div><button autoFocus onClick={onClose} aria-label="Закрыть разбор прогноза">Закрыть ×</button></header>
    <div className="personal-review-content">
      {result.error ? <div role="alert"><p>{result.error}</p><button type="button" onClick={() => setAttempt(v => v + 1)}>Повторить</button></div> : !result.data ? <p role="status">Загрузка личного прогноза…</p> : <>
        <h3>{result.data.event_name}</h3><p className="personal-review-score">{result.data.points == null ? "Ещё не рассчитан" : `${result.data.points} / ${result.data.max_points ?? "—"} баллов`}</p>
        {result.data.points != null && <ShareButton options={{kind: 'prediction', season, round}} />}
        {result.data.items.some(item => item.status === "unavailable") && <p className="personal-review-warning">Предварительный результат: часть фактов гонки ещё не подтверждена. Баллы и место могут измениться после проверки.</p>}
        <p>Угадано: {result.data.items.filter(item => item.status === "exact").length} · Частично: {result.data.items.filter(item => item.status === "partial").length} · Не угадано: {result.data.items.filter(item => item.status === "miss").length} · Ожидают данных: {result.data.items.filter(item => item.status === "unavailable").length}</p>
        {!result.data.complete && <p className="personal-review-warning">Полная разбивка этого расчёта не сохранена или результаты ещё не готовы. Неподтверждённые баллы отмечены «—». Итог взят из сохранённого результата.</p>}
        <div className="personal-review-items">{result.data.items.map(item => <article key={item.key} className={`review-${item.status}`}>
          <header><h4>{item.label}</h4><span>{statuses[item.status] ?? item.status} · {item.points ?? "—"} / {item.maximum}</span></header>
          <dl><div><dt>Ваш выбор</dt><dd>{value(item.key,item.predicted,driverNames)}</dd></div><div><dt>Фактический результат</dt><dd>{value(item.key,item.actual,driverNames)}</dd></div></dl>
          {item.position != null && <p>Ваш выбранный пилот в классификации: P{item.position}</p>}
          <p>{item.reason}</p><details><summary>Как считаются очки</summary><p>Точное совпадение: {item.rule.exact} баллов.
            {item.key === "first_retirement_driver" ? " Если несколько пилотов сошли в одной подтверждённой первой группе, выбор любого из них считается верным; баллы начисляются один раз." : ""}
            {item.rule.offsets.some(Boolean) ? ` Отклонение финишной позиции выбранного пилота на 1 / 2 / 3 места: ${item.rule.offsets.join(" / ")} балла. Большее отклонение: 0. Баллы за точность и отклонение не суммируются.` : " Нет совпадения: 0."}
            {" Если фактические данные отсутствуют, пункт не учитывается в максимуме."}</p></details>
        </article>)}</div>
        {result.data.race_facts && <section aria-label="Дополнительные данные гонки">
          <h3>Данные гонки · {result.data.race_facts.source}</h3>
          {confirmedFactsNote(result.data.race_facts.note, result.data.items) && <p>{confirmedFactsNote(result.data.race_facts.note, result.data.items)}</p>}
          {result.data.race_facts.fastest_lap && <p>Лучший круг: {result.data.race_facts.fastest_lap.driver} · {lapTime(result.data.race_facts.fastest_lap.seconds)}{optionalNumber(result.data.race_facts.fastest_lap.lap) !== null ? ` · круг ${result.data.race_facts.fastest_lap.lap}` : ''}</p>}
          {!!result.data.race_facts.laps?.length && <details><summary>Времена зачтённых кругов ({result.data.race_facts.laps.length})</summary>
            <ul>{result.data.race_facts.laps.map((lap, index) => <li key={index}>{lap.driver} · круг {lap.lap} · {lapTime(lap.seconds)}</li>)}</ul>
          </details>}
          <h4>Сходы</h4>
          {!!result.data.race_facts.first_retirement_drivers?.length && <p>Первая группа: {result.data.race_facts.first_retirement_drivers.map(code => value("first_retirement_driver", code, driverNames)).join(" · ")}.
            {result.data.race_facts.retirement_order_method === "last_lap_chronology" ? " Установлена по хронологии последних кругов." : ""}</p>}
          {!result.data.race_facts.retirement_order_confirmed && !result.data.race_facts.first_retirement_drivers?.length && <p>Точная последовательность сходов не подтверждена. Порядок списка не означает порядок сходов.</p>}
          <ul>{result.data.race_facts.retirements?.map(row => <li key={row.driver}>{row.driver} · {resultStatus(row.status)}{optionalNumber(row.laps) !== null ? ` · завершено кругов: ${row.laps}` : ""}{row.time ? ` · ${localDateTime(row.time)}` : ""}</li>)}</ul>
          <h4>Машина безопасности</h4>
          <p>{result.data.race_facts.safety_car == null ? "Нет подтверждённых данных об SC." : result.data.race_facts.safety_car ? "SC выезжала." : "Выездов SC не было."} VSC показана отдельно и не считается выездом SC.</p>
          <ul>{result.data.race_facts.safety_events?.map((event, index) => <li key={index}>{event.type} · {localDateTime(event.time)}{event.status === "7" ? " · завершение режима" : " · начало режима"}</li>)}</ul>
        </section>}
      </>}
    </div>
  </dialog>;
}
