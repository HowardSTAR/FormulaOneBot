// Country names are supplied by several schedule sources in English or Russian.
// Resolve against a closed list of locally shipped flags; never construct URLs
// from API strings. Historic races use today's national flag, as elsewhere in UI.
const countries: Record<string, readonly string[]> = {
  ae: ['United Arab Emirates', 'UAE', 'ОАЭ', 'Объединённые Арабские Эмираты'],
  ar: ['Argentina', 'Аргентина'], at: ['Austria', 'Австрия'],
  au: ['Australia', 'Австралия'], az: ['Azerbaijan', 'Азербайджан'],
  be: ['Belgium', 'Бельгия'], bh: ['Bahrain', 'Бахрейн'],
  br: ['Brazil', 'Бразилия'], ca: ['Canada', 'Канада'],
  ch: ['Switzerland', 'Швейцария'], cn: ['China', 'Китай'],
  de: ['Germany', 'West Germany', 'East Germany', 'Германия', 'ФРГ', 'ГДР'],
  es: ['Spain', 'Испания'], fr: ['France', 'Франция'],
  gb: ['United Kingdom', 'Great Britain', 'Britain', 'UK', 'Великобритания', 'Соединённое Королевство'],
  hu: ['Hungary', 'Венгрия'], in: ['India', 'Индия'],
  it: ['Italy', 'Италия'], jp: ['Japan', 'Япония'],
  kr: ['South Korea', 'Korea', 'Republic of Korea', 'Южная Корея', 'Корея'],
  ma: ['Morocco', 'Марокко'], mc: ['Monaco', 'Монако'],
  mx: ['Mexico', 'Мексика'], my: ['Malaysia', 'Малайзия'],
  nl: ['Netherlands', 'The Netherlands', 'Нидерланды', 'Голландия'],
  pt: ['Portugal', 'Португалия'], qa: ['Qatar', 'Катар'],
  ru: ['Russia', 'Russian Federation', 'Россия'],
  sa: ['Saudi Arabia', 'Саудовская Аравия'], se: ['Sweden', 'Швеция'],
  sg: ['Singapore', 'Сингапур'], tr: ['Turkey', 'Türkiye', 'Турция'],
  us: ['United States', 'United States of America', 'USA', 'US', 'США', 'Соединённые Штаты Америки'],
  za: ['South Africa', 'ЮАР', 'Южная Африка', 'Южно-Африканская Республика'],
};
const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase().replace(/[.]/g, '').replace(/\s+/g, ' ');
const codes = new Map(Object.entries(countries).flatMap(([code, names]) => [code, ...names].map(name => [normalize(name), code] as const)));
// Only unambiguous event names can fill an absent country. European/Pacific
// Grands Prix changed host countries, so they deliberately have no fallback.
const events: Record<string, string> = {
  'abu dhabi': 'ae', argentine: 'ar', austrian: 'at', australian: 'au', azerbaijan: 'az',
  belgian: 'be', bahrain: 'bh', brazilian: 'br', 'sao paulo': 'br', canadian: 'ca',
  swiss: 'ch', chinese: 'cn', german: 'de', eifel: 'de', spanish: 'es', french: 'fr',
  british: 'gb', hungarian: 'hu', indian: 'in', italian: 'it', 'emilia romagna': 'it',
  'san marino': 'it', tuscan: 'it', japanese: 'jp', korean: 'kr', moroccan: 'ma',
  monaco: 'mc', mexican: 'mx', 'mexico city': 'mx', malaysian: 'my', dutch: 'nl',
  portuguese: 'pt', qatar: 'qa', russian: 'ru', 'saudi arabian': 'sa', swedish: 'se',
  singapore: 'sg', turkish: 'tr', 'united states': 'us', 'united states west': 'us',
  miami: 'us', 'las vegas': 'us', 'caesars palace': 'us', detroit: 'us', dallas: 'us',
  'south african': 'za',
};
export function raceCountryCode(country?: string, eventName?: string): string | null {
  if (country?.trim()) return codes.get(normalize(country)) ?? null;
  const event = normalize(eventName ?? '').replace(/ grand prix$/, '');
  return events[event] ?? null;
}
