import { useLayoutEffect, type RefObject } from 'react';

/** Place the reflected light at the visible emitting control, in surface coordinates. */
export function useGameLight(surfaceRef: RefObject<HTMLDivElement | null>, selector: string, sourceKey: string) {
  useLayoutEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    let frame = 0;
    let observedSource: HTMLElement | null = null;

    const measure = () => {
      const bounds = surface.getBoundingClientRect();
      const source = Array.from(surface.querySelectorAll<HTMLElement>(selector)).find(element => element.getClientRects().length > 0);
      const light = source?.getBoundingClientRect();
      if (source !== observedSource) {
        if (observedSource) observer.unobserve(observedSource);
        if (source) observer.observe(source);
        observedSource = source ?? null;
      }
      if (!source || !light || !light.width || !bounds.width) {
        surface.style.setProperty('--game-light-opacity', '0');
        return;
      }
      // Read both boxes before changing CSS; no React updates or per-frame loop.
      surface.style.setProperty('--game-light-x', `${light.left + light.width / 2 - bounds.left}px`);
      surface.style.setProperty('--game-light-y', `${light.top + light.height / 2 - bounds.top}px`);
      surface.style.setProperty('--game-light-radius', `${Math.max(source.offsetWidth, source.offsetHeight) * 2.2}px`);
      surface.style.setProperty('--game-light-opacity', '1');
    };
    const scheduleMeasure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(scheduleMeasure);
    observer.observe(surface);
    window.addEventListener('resize', scheduleMeasure);
    measure();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('resize', scheduleMeasure);
      surface.style.removeProperty('--game-light-opacity');
      surface.style.removeProperty('--game-light-x');
      surface.style.removeProperty('--game-light-y');
      surface.style.removeProperty('--game-light-radius');
    };
  }, [surfaceRef, selector, sourceKey]);
}
