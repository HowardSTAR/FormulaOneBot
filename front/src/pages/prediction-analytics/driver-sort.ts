export type DriverSortKey = 'name' | 'team' | 'win' | 'podium' | 'top10' | 'expected' | 'dnf' | 'actual';
export type DriverSort = {key: DriverSortKey; direction: 'asc' | 'desc'};
type SortableDriver = {code: string; name: string; team: string; win: number; podium: number; top10: number; expected: number; dnf: number};
const collator = new Intl.Collator('ru', {numeric: true, sensitivity: 'base'});

export function nextDriverSort(current: DriverSort, key: DriverSortKey): DriverSort {
  return {key, direction: current.key === key ? (current.direction === 'asc' ? 'desc' : 'asc')
    : ['win', 'podium', 'top10', 'dnf'].includes(key) ? 'desc' : 'asc'};
}

export function sortDrivers<T extends SortableDriver>(drivers: readonly T[], sort: DriverSort, actual: ReadonlyMap<string, number>): T[] {
  const value = (driver: T) => sort.key === 'actual' ? actual.get(driver.code) : driver[sort.key];
  const missing = (v: unknown) => v == null || (typeof v === 'number' && !Number.isFinite(v));
  return [...drivers].sort((a, b) => {
    const av = value(a), bv = value(b);
    // An absent classification is not P0 and stays last in either direction.
    if (missing(av) !== missing(bv)) return missing(av) ? 1 : -1;
    const compared = missing(av) ? 0 : typeof av === 'string' && typeof bv === 'string'
      ? collator.compare(av, bv) : Number(av) - Number(bv);
    return compared * (sort.direction === 'asc' ? 1 : -1) || collator.compare(a.name, b.name) || collator.compare(a.code, b.code);
  });
}
