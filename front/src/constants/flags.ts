/** Маппинг национальностей (Ergast/OpenF1 API) на эмодзи флагов */
export const NATIONALITY_FLAGS: Record<string, string> = {
  British: "🇬🇧",
  "Great Britain": "🇬🇧",
  Spanish: "🇪🇸",
  German: "🇩🇪",
  French: "🇫🇷",
  Italian: "🇮🇹",
  Dutch: "🇳🇱",
  Australian: "🇦🇺",
  Monegasque: "🇲🇨",
  Thai: "🇹🇭",
  Finnish: "🇫🇮",
  Mexican: "🇲🇽",
  Canadian: "🇨🇦",
  Japanese: "🇯🇵",
  Danish: "🇩🇰",
  Argentinian: "🇦🇷",
  Argentine: "🇦🇷",
  "New Zealander": "🇳🇿",
  American: "🇺🇸",
  Chinese: "🇨🇳",
  Brazilian: "🇧🇷",
  Austrian: "🇦🇹",
  Belgian: "🇧🇪",
  Venezuelan: "🇻🇪",
  Polish: "🇵🇱",
  Russian: "🇷🇺",
  Swiss: "🇨🇭",
  Swedish: "🇸🇪",
  Irish: "🇮🇪",
  Portuguese: "🇵🇹",
  Hungarian: "🇭🇺",
  "South African": "🇿🇦",
  Indian: "🇮🇳",
  Indonesian: "🇮🇩",
  Malaysian: "🇲🇾",
  Colombian: "🇨🇴",
  Chilean: "🇨🇱",
  Uruguayan: "🇺🇾",
  Rhodesian: "🇿🇼",
  "East German": "🇩🇪",
  Liechtensteiner: "🇱🇮",
  Czech: "🇨🇿",
  Singaporean: "🇸🇬",
  Emirati: "🇦🇪",
  Korean: "🇰🇷",
};

export function getNationalityWithFlag(nationality: string): string {
  if (!nationality) return "";
  const flag = getFlagForNationality(nationality);
  return flag ? `${flag} ${nationality}` : nationality;
}

/** Поиск флага по национальности без учёта регистра */
export function getFlagForNationality(nationality: string): string {
  if (!nationality) return "";
  const direct = NATIONALITY_FLAGS[nationality];
  if (direct) return direct;
  const lower = nationality.toLowerCase();
  const key = Object.keys(NATIONALITY_FLAGS).find((k) => k.toLowerCase() === lower);
  return key ? NATIONALITY_FLAGS[key] : "";
}
