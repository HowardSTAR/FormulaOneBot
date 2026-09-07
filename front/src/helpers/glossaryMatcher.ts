import { GLOSSARY_ITEMS } from "../constants/glossaryData.ts";

const aliases: Record<string, string[]> = {
  "formula-one": ["Формулы-1"],
  undercut: ["андерката"],
  "active-aero": ["активной аэродинамики"],
  qualifying: ["квалификации", "квалификацией"],
  "pole-position": ["поул", "поула", "поулы"],
  "pit-stop": ["пит-стопа", "пит-стопы", "пит-стопов"],
  "safety-car": ["сейфти-кар"],
  "fastest-lap": ["лучшего круга", "лучшие круги"],
  sprint: ["спринты", "спринта"],
  drs: ["DRS"],
};
const terms = new Map(GLOSSARY_ITEMS.flatMap(item =>
  [item.termRu, ...item.termEn.split(" / "), ...(Object.hasOwn(aliases, item.id) ? aliases[item.id] : [])]
    .map(term => [term.toLocaleLowerCase("ru"), item] as const),
));
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const pattern = [...terms.keys()].sort((a, b) => b.length - a.length).map(escape).join("|");

/** Match complete words (including Cyrillic), preferring the longest phrase. */
export function splitGlossaryText(text: string) {
  const regex = new RegExp(`(?<![\\p{L}\\p{N}_-])(${pattern})(?![\\p{L}\\p{N}_-])`, "giu");
  const parts: Array<{ text: string; item?: typeof GLOSSARY_ITEMS[number] }> = [];
  let offset = 0;
  for (const match of text.matchAll(regex)) {
    const index = match.index;
    if (index > offset) parts.push({ text: text.slice(offset, index) });
    parts.push({ text: match[0], item: terms.get(match[0].toLocaleLowerCase("ru")) });
    offset = index + match[0].length;
  }
  if (offset < text.length) parts.push({ text: text.slice(offset) });
  return parts;
}
