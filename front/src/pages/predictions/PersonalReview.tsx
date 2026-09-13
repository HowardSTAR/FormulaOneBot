import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../../helpers/api";
import "./personal-review.css";

type Item = { key: string; label: string; predicted: string | number | null; actual: string | number | null;
  position: number | null; points: number | null; maximum: number; status: string; reason: string;
  rule: { exact: number; offsets: number[] } };
type Review = { event_name: string; points: number | null; max_points: number | null; complete: boolean; items: Item[] };
const statuses: Record<string,string> = { exact: "Угадано", partial: "Частичное попадание", miss: "Не угадано", unavailable: "Нет данных", unknown: "Не подтверждено" };
function value(key: string, v: string | number | null) {
  if (v === null || v === "") return "—";
  return key === "safety_car" ? (Number(v) ? "Да" : "Нет") : String(v);
}

export function PersonalReview({ season, round, onClose }: { season: number; round: number; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [result, setResult] = useState<{ data?: Review; error?: string }>({});
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    element?.showModal();
    let active = true;
    apiRequest<Review>(`/api/predictions/mine/${season}/${round}`).then(data => { if (active) setResult({ data }); })
      .catch(error => { if (active) setResult({ error: error instanceof Error ? error.message : "Не удалось загрузить прогноз" }); });
    return () => { active = false; element?.close(); previous?.focus(); };
  }, [season, round]);
  return <dialog ref={dialog} className="personal-review" aria-labelledby="personal-review-title" onCancel={onClose}>
    <header><div><small>Только для вас · {season} · этап {round}</small><h2 id="personal-review-title">Мой прогноз</h2></div><button autoFocus onClick={onClose} aria-label="Закрыть разбор прогноза">Закрыть ×</button></header>
    <div className="personal-review-content">
      {result.error ? <p role="alert">{result.error}</p> : !result.data ? <p role="status">Загрузка личного прогноза…</p> : <>
        <h3>{result.data.event_name}</h3><p className="personal-review-score">{result.data.points === null ? "Ещё не рассчитан" : `${result.data.points} / ${result.data.max_points} баллов`}</p>
        {!result.data.complete && <p className="personal-review-warning">Полная разбивка этого расчёта не сохранена или результаты ещё не готовы. Неподтверждённые баллы отмечены «—». Итог взят из сохранённого результата.</p>}
        <div className="personal-review-items">{result.data.items.map(item => <article key={item.key} className={`review-${item.status}`}>
          <header><h4>{item.label}</h4><span>{statuses[item.status] ?? item.status} · {item.points ?? "—"} / {item.maximum}</span></header>
          <dl><div><dt>Ваш выбор</dt><dd>{value(item.key,item.predicted)}</dd></div><div><dt>Фактический результат</dt><dd>{value(item.key,item.actual)}</dd></div></dl>
          {item.position !== null && <p>Ваш выбранный пилот в классификации: P{item.position}</p>}
          <p>{item.reason}</p><details><summary>Как считаются очки</summary><p>Точное совпадение: {item.rule.exact} баллов.
            {item.rule.offsets.some(Boolean) ? ` Отклонение финишной позиции выбранного пилота на 1 / 2 / 3 места: ${item.rule.offsets.join(" / ")} балла. Большее отклонение: 0. Баллы за точность и отклонение не суммируются.` : " Нет совпадения: 0."}
            {" Если фактические данные отсутствуют, пункт не учитывается в максимуме."}</p></details>
        </article>)}</div>
      </>}
    </div>
  </dialog>;
}
