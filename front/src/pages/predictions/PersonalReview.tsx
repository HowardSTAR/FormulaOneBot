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
const statuses: Record<string,string> = { exact: "Угадано", partial: "Частично", miss: "Не угадано", unavailable: "Ожидаем данные", unknown: "Нет разбивки" };
const filters = [{key: 'exact', label: 'Угадано', icon: '✓'}, {key: 'partial', label: 'Частично', icon: '≈'},
  {key: 'miss', label: 'Не угадано', icon: '×'}, {key: 'waiting', label: 'Ожидают данных', icon: '…'},
  {key: 'unknown', label: 'Нет разбивки', icon: '—'}];
function matchesFilter(status: string, filter: string) {
  return filter === 'all' || (filter === 'waiting' ? status === 'unavailable' : status === filter);
}
function value(key: string, v: string | number | string[] | null, names: Record<string, string>): string {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.map(code => value(key, code, names)).join(" · ");
  if (key === "safety_car") return Number(v) ? "Да" : "Нет";
  const code = String(v);
  return names[code.toUpperCase()] ? `${names[code.toUpperCase()]} (${code})` : code;
}

export function PersonalReview({ season, round, onClose }: { season: number; round: number; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [resultState, setResult] = useState<{ key: string; data?: Review; error?: string }>({ key: '' });
  const [driverNames, setDriverNames] = useState<Record<string, string>>({});
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState('all');
  const requestKey = `${season}:${round}:${attempt}`;
  const result: { data?: Review; error?: string } = resultState.key === requestKey ? resultState : {};
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    element?.showModal();
    let active = true;
    apiRequest<Review>(`/api/predictions/mine/${season}/${round}`).then(data => { if (active) setResult({ key: requestKey, data }); })
      .catch(error => { if (active) setResult({ key: requestKey, error: error instanceof Error ? error.message : "Не удалось загрузить прогноз" }); });
    apiRequest<{drivers?: {code: string; name: string}[]}>('/api/drivers', {season})
      .then(data => { if (active) setDriverNames(Object.fromEntries((data.drivers || []).filter(driver => driver.code && driver.name).map(driver => [driver.code.toUpperCase(), driver.name.trim()]))); })
      .catch(() => { if (active) setDriverNames({}); });
    return () => { active = false; element?.close(); previous?.focus(); };
  }, [season, round, requestKey]);
  const items = result.data?.items ?? [];
  const visibleItems = items.filter(item => matchesFilter(item.status, filter));
  return <dialog ref={dialog} className="personal-review" aria-labelledby="personal-review-title" onCancel={onClose}>
    <header className="review-dialog-header"><div><small className="review-eyebrow">Личный разбор · {season} · этап {round}</small><h2 id="personal-review-title">Мой прогноз</h2></div><button className="review-close" type="button" autoFocus onClick={onClose} aria-label="Закрыть разбор прогноза"><span>Закрыть</span><span aria-hidden="true">×</span></button></header>
    <div className="personal-review-content">
      {result.error ? <div className="review-feedback" role="alert"><h3>Не удалось загрузить разбор</h3><p>{result.error}</p><button type="button" onClick={() => setAttempt(v => v + 1)}>Повторить</button></div> : !result.data ? <div className="review-feedback" role="status"><p>Загрузка личного прогноза…</p></div> : <>
        <section className="review-summary" aria-label="Итог этапа"><div><span className="review-eyebrow">Результат этапа</span><h3>{result.data.event_name}</h3>
          {result.data.points == null ? <p className="review-pending">Ещё не рассчитан</p> : <p className="personal-review-score"><strong>{result.data.points}</strong><span>/ {result.data.max_points ?? '—'}<small>баллов</small></span></p>}
          {result.data.points != null && result.data.max_points != null && result.data.max_points > 0 && <div className="review-score-track" role="meter" aria-label="Баллы за этап" aria-valuemin={0} aria-valuemax={result.data.max_points} aria-valuenow={result.data.points}><span style={{width: `${Math.max(0, Math.min(100, result.data.points / result.data.max_points * 100))}%`}} /></div>}
        </div><div className="review-summary-action">{result.data.points != null && <ShareButton options={{kind: 'prediction', season, round}} />}<small>Разбор и ваши ответы видны только вам.</small></div></section>
        {items.some(item => item.status === 'unavailable') && <p className="personal-review-warning"><strong>Результат предварительный.</strong> Часть фактов ещё не подтверждена. Баллы и место могут измениться после проверки.</p>}
        <div className="review-filters" role="group" aria-label="Показать категории по результату">{filters.map(entry => <button type="button" key={entry.key} className={`review-filter filter-${entry.key}`} aria-pressed={filter === entry.key} onClick={() => setFilter(current => current === entry.key ? 'all' : entry.key)}><span className="review-filter-icon" aria-hidden="true">{entry.icon}</span><span>{entry.label}<strong>{items.filter(item => matchesFilter(item.status, entry.key)).length}</strong></span></button>)}</div>
        {!result.data.complete && items.some(item => item.status === 'unknown') && <p className="personal-review-warning">Часть исторической разбивки не удалось восстановить по сохранённым данным. Эти баллы отмечены «—». Итог взят из сохранённого результата; подтверждать факты гонки для этой разбивки не требуется.</p>}
        <header className="review-list-heading"><div><h3>По категориям</h3><p aria-live="polite">{filter === 'all' ? `Все категории: ${items.length}` : `Показано: ${visibleItems.length} из ${items.length}`}</p></div><button className="review-show-all" type="button" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>Все категории</button></header>
        <div className="personal-review-items">{visibleItems.map(item => <article key={item.key} className={`review-item review-${item.status}`}>
          <header><div className="review-item-heading"><span className="review-item-number" aria-hidden="true">{String(items.indexOf(item) + 1).padStart(2, '0')}</span><h4>{item.label}</h4></div><div className="review-item-result"><span className="review-status">{statuses[item.status] ?? item.status}</span><span className="review-item-points"><strong>{item.points ?? '—'}</strong> / {item.maximum}<small>баллов</small></span></div></header>
          <dl className="review-comparison"><div><dt>Ваш прогноз</dt><dd>{value(item.key,item.predicted,driverNames)}</dd></div><div><dt>Результат гонки</dt><dd>{value(item.key,item.actual,driverNames)}</dd></div></dl>
          <div className="review-explanation">{item.position != null && <p className="review-position">Ваш пилот в классификации: <strong>P{item.position}</strong></p>}<p className="review-reason">{item.reason}</p></div>
          <details className="review-rule"><summary>Как считаются очки</summary><ul><li>Точное совпадение: <strong>{item.rule.exact} баллов</strong>.</li>
            {item.key === "first_retirement_driver" && <li>Если несколько пилотов сошли в одной подтверждённой первой группе, выбор любого из них считается верным. Баллы начисляются один раз.</li>}
            {item.rule.offsets.some(Boolean) ? <><li>Отклонение финишной позиции на 1 / 2 / 3 места: <strong>{item.rule.offsets.join(' / ')} балла</strong>. Большее отклонение: 0.</li><li>Баллы за точность и отклонение не суммируются.</li></> : <li>Нет совпадения: 0.</li>}
            <li>Если фактические данные отсутствуют, пункт не учитывается в максимуме.</li></ul></details>
        </article>)}</div>
        {visibleItems.length === 0 && <p className="review-empty">{items.length === 0 ? 'Подробности расчёта пока не сохранены.' : 'В этой группе нет категорий. Выберите другой результат или покажите все категории.'}</p>}
        {result.data.race_facts && <details className="review-facts" aria-label="Дополнительные данные гонки"><summary>Данные гонки<span>Источники, круги и сходы</span></summary><div className="review-facts-content">
          <p className="review-facts-source">Источник: {result.data.race_facts.source}</p>
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
        </div></details>}
      </>}
    </div>
  </dialog>;
}
