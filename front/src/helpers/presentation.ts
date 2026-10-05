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

// These are fixed offsets. Use places without seasonal clock changes so the
// city examples stay accurate year-round (IANA tzdb, checked October 2026).
const FIXED_TIMEZONE_PLACES: Record<string, string> = {
  'Etc/GMT+12': 'острова Бейкер и Хауленд',
  'Etc/GMT+11': 'Паго-Паго',
  'Etc/GMT+10': 'Гонолулу',
  'Etc/GMT+9': 'Рикитеа',
  'Etc/GMT+8': 'Адамстаун',
  'Etc/GMT+7': 'Финикс',
  'Etc/GMT+6': 'Гватемала',
  'Etc/GMT+5': 'Богота, Лима',
  'Etc/GMT+4': 'Санто-Доминго',
  'Etc/GMT+3': 'Буэнос-Айрес',
  'Etc/GMT+2': 'Фернанду-ди-Норонья',
  'Etc/GMT+1': 'Прая',
  UTC: 'Рейкьявик, Аккра',
  'Etc/GMT-1': 'Лагос, Алжир',
  'Etc/GMT-2': 'Йоханнесбург',
  'Etc/GMT-3': 'Москва, Стамбул',
  'Etc/GMT-4': 'Дубай, Баку',
  'Etc/GMT-5': 'Ташкент',
  'Etc/GMT-6': 'Дакка, Бишкек',
  'Etc/GMT-7': 'Бангкок, Джакарта',
  'Etc/GMT-8': 'Пекин, Сингапур',
  'Etc/GMT-9': 'Токио, Сеул',
  'Etc/GMT-10': 'Владивосток',
  'Etc/GMT-11': 'Магадан, Нумеа',
  'Etc/GMT-12': 'Сува, Тарава',
};

export function timezoneName(zone: string, date = new Date()): string {
  try {
    const offset = new Intl.DateTimeFormat("en", { timeZone: zone, timeZoneName: "longOffset" }).formatToParts(date).find(part => part.type === "timeZoneName")?.value?.replace("GMT", "UTC") ?? "";
    const place = FIXED_TIMEZONE_PLACES[zone] ?? (zone === 'Europe/Moscow' ? 'Москва' : zone.startsWith('Etc/') ? '' : zone.split('/').at(-1)?.replaceAll('_', ' '));
    return `${offset === 'UTC' ? 'UTC+00:00' : offset}${place ? ` · ${place}` : ''}`;
  } catch { return zone; }
}

export const FIXED_TIMEZONE_OPTIONS = Object.keys(FIXED_TIMEZONE_PLACES).map(value => ({ value, label: timezoneName(value) }));

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
  const confirmed = ["fastest_lap_driver", "first_retirement_driver", "safety_car"].every(key => items.some(item => item.key === key && item.actual != null && item.actual !== "" && item.status !== "unavailable"));
  if (!confirmed) return note ?? "";
  return (note ?? "").replace(/Источник не предоставил статусы сессии; дополнительные факты не подтверждены\.?/g, "").trim();
}
