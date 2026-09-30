import { useCallback, useMemo, useSyncExternalStore } from 'react';

/** Match CSS breakpoints without mounting a second, hidden application tree. */
export function useMediaQuery(query: string): boolean {
  const media = useMemo(() => window.matchMedia(query), [query]);
  const subscribe = useCallback((listener: () => void) => {
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [media]);
  return useSyncExternalStore(subscribe, () => media.matches, () => false);
}
