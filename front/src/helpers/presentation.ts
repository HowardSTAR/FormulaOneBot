export function optionalNumber(value: unknown): number | null {
  if (value == null || (typeof value === 'string' && !value.trim()) || typeof value === "boolean") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function localDateTime(value?: string | null, timeZone?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  try { return date.toLocaleString("ru-RU", { timeZone, day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }); }
  catch { return date.toLocaleString("ru-RU"); }
}

export function timezoneName(zone: string, date = new Date()): string {
  try {
    const offset = new Intl.DateTimeFormat("en", { timeZone: zone, timeZoneName: "longOffset" }).formatToParts(date).find(part => part.type === "timeZoneName")?.value?.replace("GMT", "UTC") ?? "";
    return `${offset}${zone === "Europe/Moscow" || zone === "Etc/GMT-3" ? ' · Москва' : zone.startsWith('Etc/') ? '' : ` · ${zone.split('/').at(-1)?.replaceAll('_', ' ')}`}`;
  } catch { return zone; }
}

export function daysUntil(value: string, now = Date.now()): number | null {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, Math.ceil((timestamp - now) / 86_400_000)) : null;
}

export function resultStatus(value?: string | null): string {
  const labels: Record<string, string> = { Finished: "Финишировал", Retired: "Сход", Disqualified: "Дисквалификация", "Not classified": "Не классифицирован", "Did not start": "Не стартовал", Accident: "Авария", Collision: "Столкновение", Engine: "Двигатель", Gearbox: "Коробка передач", Suspension: "Подвеска" };
  if (!value) return "—";
  if (/^\+\d+ Laps?$/i.test(value)) return `${value.match(/\d+/)?.[0]} круг(а) отставания`;
  return labels[value] ?? value;
}

export function cleanBiography(value: string): string {
  return value.replace(/\[(?:\d+(?:[,–-]\d+)*|…|\.\.\.)\]/g, "").replace(/\s+([,.])/g, "$1").trim();
}

export function confirmedFactsNote(note: string | undefined, items: {key: string; actual: unknown; status: string}[]): string {
  const confirmed = ["fastest_lap_driver", "first_retirement_driver", "safety_car"].every(key => items.some(item => item.key === key && item.actual != null && item.actual !== "" && !["unknown", "unavailable"].includes(item.status)));
  if (!confirmed) return note ?? "";
  return (note ?? "").replace(/Источник не предоставил статусы сессии; дополнительные факты не подтверждены\.?/g, "").trim();
}
