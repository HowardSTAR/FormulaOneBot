export type RaceHighlight = {
  title: string; url: string; publisher: string; published_at: string;
  category: string; driver_code: string; score: number; published: number;
};

export function selectRaceHighlights(candidates: RaceHighlight[], favoriteDrivers: string[], limit = 4) {
  const codes = new Set(favoriteDrivers.map(code => code.toUpperCase()));
  const ranked = candidates.filter(item => item.category === 'incident' || item.category === 'penalty'
    || item.category === 'retained_overtake' && codes.has(item.driver_code))
    .sort((a, b) => b.score - a.score || a.published - b.published || a.url.localeCompare(b.url));
  const seen = new Set<string>();
  const unique = ranked.filter(item => {
    const key = JSON.stringify([item.category, item.title]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const selected: RaceHighlight[] = [];
  const categories = new Set<string>();
  for (const item of unique) {
    if (!categories.has(item.category)) {selected.push(item); categories.add(item.category);}
    if (selected.length === limit) break;
  }
  for (const item of unique) {
    if (selected.length === limit) break;
    if (!selected.includes(item)) selected.push(item);
  }
  return selected.sort((a, b) => a.published - b.published || a.url.localeCompare(b.url));
}
