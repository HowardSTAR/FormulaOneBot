const API_BASE = (import.meta.env.VITE_API_URL as string) || "";
const PATH_BASE = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");

/** Маппинг национальностей (Ergast/OpenF1 API) на ISO-код страны */
export const NATIONALITY_FLAG_CODES: Record<string, string> = {
  British: "gb",
  "Great Britain": "gb",
  Spanish: "es",
  German: "de",
  French: "fr",
  Italian: "it",
  Dutch: "nl",
  Australian: "au",
  Monegasque: "mc",
  Thai: "th",
  Finnish: "fi",
  Mexican: "mx",
  Canadian: "ca",
  Japanese: "jp",
  Danish: "dk",
  Argentinian: "ar",
  Argentine: "ar",
  "New Zealander": "nz",
  American: "us",
  Chinese: "cn",
  Brazilian: "br",
  Austrian: "at",
  Belgian: "be",
  Venezuelan: "ve",
  Polish: "pl",
  Russian: "ru",
  Swiss: "ch",
  Swedish: "se",
  Irish: "ie",
  Portuguese: "pt",
  Hungarian: "hu",
  "South African": "za",
  Indian: "in",
  Indonesian: "id",
  Malaysian: "my",
  Colombian: "co",
  Chilean: "cl",
  Uruguayan: "uy",
  Rhodesian: "zw",
  "East German": "de",
  Liechtensteiner: "li",
  Czech: "cz",
  Singaporean: "sg",
  Emirati: "ae",
  Korean: "kr",
};

export function getCountryFlagUrl(countryCode: string): string {
  const normalized = (countryCode || "").trim().toLowerCase();
  if (!normalized) return "";
  const origin = API_BASE || (typeof window !== "undefined" ? window.location.origin : "");
  const path = `${PATH_BASE}/assets/country/${normalized}.svg`.replace(/\/+/g, "/");
  return `${origin.replace(/\/$/, "")}${path}`;
}

/** Поиск ISO-кода флага по национальности без учёта регистра */
export function getFlagCodeForNationality(nationality: string): string {
  if (!nationality) return "";
  const direct = NATIONALITY_FLAG_CODES[nationality];
  if (direct) return direct;
  const lower = nationality.toLowerCase();
  const key = Object.keys(NATIONALITY_FLAG_CODES).find((k) => k.toLowerCase() === lower);
  return key ? NATIONALITY_FLAG_CODES[key] : "";
}

export function getFlagUrlForNationality(nationality: string): string {
  const code = getFlagCodeForNationality(nationality);
  return code ? getCountryFlagUrl(code) : "";
}
