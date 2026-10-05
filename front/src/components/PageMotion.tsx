import { useLayoutEffect, useRef, type RefObject } from 'react';
import { useViewTransitionState } from 'react-router-dom';
import { pageMotionDirection, preparePageMotion } from '../helpers/pageMotion';
import './page-motion.css';

// A marker inside Suspense starts motion only when the lazy page is ready.
// Animate the existing section so direct-child layouts and sticky controls survive.
export function PageMotion({ pathname, previousPathRef }: { pathname: string; previousPathRef: RefObject<string | null> }) {
  const marker = useRef<HTMLSpanElement>(null);
  const nativeTransition = useViewTransitionState(pathname);
  useLayoutEffect(() => {
    const from = previousPathRef.current;
    previousPathRef.current = pathname;
    if (from && from !== pathname) preparePageMotion(from, pathname);
    const page = marker.current?.parentElement;
    if (!page || !from || from === pathname || nativeTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const direction = pageMotionDirection(from, pathname);
    const animation = page.animate([
      { opacity: 0, transform: `translateX(${direction * 36}px)` },
      { opacity: 1, transform: 'translateX(0)' },
    ], { duration: 260, easing: 'cubic-bezier(.22, 1, .36, 1)' });
    return () => animation.cancel();
  }, [pathname, previousPathRef, nativeTransition]);
  return <span hidden aria-hidden="true" ref={marker} />;
}
