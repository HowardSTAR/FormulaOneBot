import { useEffect, useLayoutEffect, useRef } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';
import { pageTitle } from '../helpers/pageTitles';
const positions = new Map<string, number>();
export function RouteContext() {
  const location = useLocation();
  const navigation = useNavigationType();
  const previousPath = useRef(location.pathname);
  useEffect(() => {
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = 'manual';
    return () => { window.history.scrollRestoration = previous; };
  }, []);
  useEffect(() => { document.title = pageTitle(location.pathname); }, [location.pathname]);
  useLayoutEffect(() => {
    const target = navigation === 'POP' ? positions.get(location.key) : undefined;
    const samePage = previousPath.current === location.pathname;
    previousPath.current = location.pathname;
    const restore = () => {
      if (document.documentElement.dataset.onboardingActive) return;
      if (target != null) window.scrollTo(0, target);
      else if (!samePage) window.scrollTo(0, 0);
    };
    restore();
    // Page chunks and API responses can increase the height after navigation.
    const observer = target != null ? new ResizeObserver(() => {
      restore();
      if (document.documentElement.scrollHeight - window.innerHeight >= target) observer?.disconnect();
    }) : null;
    observer?.observe(document.body);
    const timeout = window.setTimeout(() => observer?.disconnect(), 20000);
    positions.set(location.key, window.scrollY);
    const remember = () => positions.set(location.key, window.scrollY);
    const stopRestoring = () => observer?.disconnect();
    window.addEventListener('scroll', remember, {passive: true});
    window.addEventListener('wheel', stopRestoring, {passive: true});
    window.addEventListener('touchstart', stopRestoring, {passive: true});
    window.addEventListener('keydown', stopRestoring);
    return () => {
      if (positions.size > 100) positions.delete(positions.keys().next().value!);
      window.removeEventListener('scroll', remember);
      window.removeEventListener('wheel', stopRestoring);
      window.removeEventListener('touchstart', stopRestoring);
      window.removeEventListener('keydown', stopRestoring);
      observer?.disconnect(); window.clearTimeout(timeout);
    };
  }, [location.key, location.pathname, navigation]);
  return null;
}
