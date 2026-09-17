export type PersonalPrediction = {
  season?: number;
  round?: number;
  status: string;
  event_name?: string;
  is_open: boolean;
  deadline_utc?: string | null;
  opens_at_utc?: string | null;
  prediction: { points?: number | null; max_points?: number | null } | null;
};

export function predictionSummary(data: PersonalPrediction, now: number) {
  const deadline = Date.parse(data.deadline_utc || '');
  const opens = Date.parse(data.opens_at_utc || '');
  if (data.status !== 'ok') return { title: 'Ожидаем следующий этап', action: 'История прогнозов', urgent: false };
  if (data.prediction?.points != null) return { title: `Ваш результат: ${data.prediction.points} очк.`, action: 'Посмотреть разбор', urgent: false };
  const open = data.is_open && Number.isFinite(deadline) && now < deadline;
  if (open) return {
    title: data.prediction ? 'Прогноз сохранён' : 'Вы ещё не сделали прогноз',
    action: data.prediction ? 'Проверить прогноз' : 'Сделать прогноз',
    urgent: deadline - now <= 2 * 60 * 60 * 1000,
  };
  if (Number.isFinite(opens) && now < opens) return { title: 'Приём ещё не открыт', action: 'Открыть прогнозы', urgent: false };
  return { title: data.prediction ? 'Прогноз принят · ждём итоги' : 'Приём закрыт', action: 'Открыть прогнозы', urgent: false };
}
