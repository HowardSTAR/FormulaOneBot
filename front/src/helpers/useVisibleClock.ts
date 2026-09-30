import { useEffect, useState } from 'react';
import { visibleInterval } from './visibleInterval';

export function useVisibleClock(delay: number, enabled = true): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (enabled) return visibleInterval(() => setNow(Date.now()), delay);
  }, [delay, enabled]);
  return now;
}
