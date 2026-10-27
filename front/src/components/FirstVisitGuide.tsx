import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuthState } from '../helpers/auth';
import { HomeIcon } from '../pages/index/HomeIcon';
import { useHeroData } from '../context/useHeroData';
import { formatTimezoneLabel, getDisplayTimezone } from '../helpers/timezone';
import { ONBOARDING_CHANGED, ONBOARDING_START, onboardingSteps, readOnboarding, saveOnboarding } from '../helpers/onboarding';
import './first-visit-guide.css';

type Phase = 'leaving' | 'loading' | 'entering' | 'ready';
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** A guided workspace: the real page scrolls beside/above the instructions. */
export function FirstVisitGuide() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { loaded } = useHeroData();
  const auth = useAuthState();
  const steps = useMemo(() => onboardingSteps.filter(item => !('memberOnly' in item) || auth.signedIn), [auth.signedIn]);
  const [stage, setStage] = useState<number | null>(() => readOnboarding() ? null : 0);
  const [started, setStarted] = useState(false);
  const [phase, setPhase] = useState<Phase>('loading');
  const phaseRef = useRef<Phase>('loading');
  const changingRoute = useRef(false);
  const changeTimer = useRef<number | null>(null);
  const panel = useRef<HTMLElement>(null);
  const active = stage !== null && auth.loaded && (started || pathname === '/' && loaded);
  // A sign-in change can shorten the tour while it is open.
  const currentStage = Math.min(stage ?? 0, steps.length - 1);
  const step = steps[currentStage];
  const timezone = formatTimezoneLabel(getDisplayTimezone());
  const updatePhase = useCallback((next: Phase) => { phaseRef.current = next; setPhase(next); }, []);

  const finish = useCallback((status: 'completed' | 'skipped') => {
    if (changeTimer.current !== null) window.clearTimeout(changeTimer.current);
    changingRoute.current = false;
    saveOnboarding(status);
    setStage(null);
    setStarted(false);
    updatePhase('loading');
    if (status === 'completed') navigate('/', { replace: true });
  }, [navigate, updatePhase]);

  useEffect(() => {
    const start = () => {
      if (changeTimer.current !== null) window.clearTimeout(changeTimer.current);
      changingRoute.current = true;
      setStarted(true);
      setStage(0);
      updatePhase('loading');
      navigate(steps[0].route, { replace: true });
    };
    window.addEventListener(ONBOARDING_START, start);
    return () => window.removeEventListener(ONBOARDING_START, start);
  }, [navigate, steps, updatePhase]);

  const goTo = (index: number) => {
    if (!active) {
      setStarted(true);
      setStage(index);
      updatePhase('loading');
      navigate(steps[index].route, { replace: true });
      return;
    }
    if (phaseRef.current !== 'ready') return;
    setStarted(true);
    changingRoute.current = true;
    updatePhase('leaving');
    changeTimer.current = window.setTimeout(() => {
      setStage(index);
      updatePhase('loading');
      navigate(steps[index].route, { replace: true });
    }, reducedMotion() ? 0 : 180);
  };

  useLayoutEffect(() => {
    if (!active) return;
    const root = document.documentElement;
    const previousFocus = document.activeElement;
    const overflow = root.style.overflow;
    const previousHeight = root.style.getPropertyValue('--onboarding-panel-height');
    root.style.overflow = 'hidden';
    root.dataset.onboardingActive = 'true';
    const measure = () => root.style.setProperty('--onboarding-panel-height', `${panel.current?.offsetHeight || 210}px`);
    measure();
    const observer = new ResizeObserver(measure);
    if (panel.current) observer.observe(panel.current);
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') finish('skipped'); };
    window.addEventListener('keydown', escape);
    window.dispatchEvent(new Event(ONBOARDING_CHANGED));
    panel.current?.focus({ preventScroll: true });
    return () => {
      observer.disconnect();
      window.removeEventListener('keydown', escape);
      if (changeTimer.current !== null) window.clearTimeout(changeTimer.current);
      root.style.overflow = overflow;
      if (previousHeight) root.style.setProperty('--onboarding-panel-height', previousHeight);
      else root.style.removeProperty('--onboarding-panel-height');
      delete root.dataset.onboardingActive;
      delete root.dataset.onboardingPhase;
      window.dispatchEvent(new Event(ONBOARDING_CHANGED));
      if (previousFocus instanceof HTMLElement && previousFocus !== document.body && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [active, finish]);

  useLayoutEffect(() => {
    if (active) document.documentElement.dataset.onboardingPhase = phase;
  }, [active, phase]);

  useEffect(() => {
    if (!active || pathname === step.route || changingRoute.current) return;
    // Follow page navigation, including deliberate exits to detail pages.
    const index = steps.findIndex(item => item.route === pathname);
    const frame = requestAnimationFrame(() => {
      if (index < 0) finish('skipped');
      else { setStage(index); updatePhase('loading'); }
    });
    return () => cancelAnimationFrame(frame);
  }, [active, pathname, step.route, steps, finish, updatePhase]);

  useEffect(() => {
    if (!active || pathname !== step.route) return;
    const preview = document.querySelector<HTMLElement>('.app-content');
    const scope = document.querySelector<HTMLElement>('.app-page-main');
    const toolbar = preview?.querySelector<HTMLElement>('.home-header-row, .account-shortcut-bar');
    let target: HTMLElement | undefined;
    let prepared = false;
    let positionTargets: HTMLElement[] = [];
    let scrollingFrame: number | undefined;
    const frameElement = document.createElement('div');
    frameElement.className = 'first-visit-target-frame';
    frameElement.setAttribute('aria-hidden', 'true');
    document.body.append(frameElement);
    const measure = () => {
      if (!target || !preview || !target.isConnected) { frameElement.hidden = true; return; }
      const rect = target.getBoundingClientRect(), viewport = preview.getBoundingClientRect();
      const left = Math.max(rect.left - 5, viewport.left + 4);
      const toolbarBottom = toolbar?.getBoundingClientRect().bottom ?? viewport.top;
      const top = Math.max(rect.top - 5, viewport.top + 4, toolbarBottom + 8);
      const right = Math.min(rect.right + 5, viewport.right - 4, window.innerWidth - 4);
      const bottom = Math.min(rect.bottom + 5, viewport.bottom - 4, window.innerHeight - 4);
      frameElement.hidden = right <= left || bottom <= top;
      Object.assign(frameElement.style, { left: `${left}px`, top: `${top}px`, width: `${Math.max(0, right - left)}px`, height: `${Math.max(0, bottom - top)}px` });
    };
    const requestMeasure = () => {
      if (scrollingFrame !== undefined) cancelAnimationFrame(scrollingFrame);
      scrollingFrame = requestAnimationFrame(measure);
    };
    const sizes = new ResizeObserver(requestMeasure);
    if (scope) sizes.observe(scope);
    if (preview) sizes.observe(preview);
    preview?.addEventListener('scroll', requestMeasure, { passive: true });
    window.addEventListener('resize', requestMeasure);
    let enterTimer: number | undefined;
    const unmark = () => {
      target?.classList.remove('first-visit-highlight');
      if (target) { delete target.dataset.tourRoute; sizes.unobserve(target); }
      positionTargets.forEach(node => node.classList.remove('first-visit-position'));
      positionTargets = [];
    };
    const prepare = () => {
      if (!preview || !scope || scope.querySelector('.route-loading')) return;
      const visible = (node: HTMLElement) => node.getBoundingClientRect().height > 0 && getComputedStyle(node).visibility !== 'hidden';
      // Selectors are ordered by teaching priority, rather than DOM order.
      const candidate = step.target.split(',').flatMap(selector => Array.from(scope.querySelectorAll<HTMLElement>(selector.trim())).filter(visible))[0]
        || Array.from(scope.querySelectorAll<HTMLElement>('h1, h2')).find(visible);
      if (!candidate) return;
      if (candidate !== target) {
        unmark();
        target = candidate;
        target.classList.add('first-visit-highlight');
        target.dataset.tourRoute = step.route;
        sizes.observe(target);
        prepared = false;
      }
      if ('positions' in step) {
        positionTargets = Array.from(scope.querySelectorAll<HTMLElement>(step.positions));
        positionTargets.forEach(node => node.classList.add('first-visit-position'));
      }
      requestMeasure();
      if (prepared) return;
      prepared = true;
      preview.scrollTo({ top: 0, behavior: 'instant' });
      const rect = target.getBoundingClientRect();
      const targetTop = rect.top - preview.getBoundingClientRect().top;
      // Keep the heading and surrounding context when the control is already
      // visible. Only bring deeper sections to the top of the workspace.
      const toolbarSpace = toolbar ? toolbar.offsetHeight + (parseFloat(getComputedStyle(toolbar).top) || 0) + 16 : 0;
      const top = rect.height > (preview.clientHeight - toolbarSpace) * .5
        ? Math.max(0, targetTop - toolbarSpace - 20)
        : Math.max(0, targetTop + rect.height - preview.clientHeight + 20);
      preview.scrollTo({ top, behavior: reducedMotion() ? 'instant' : 'smooth' });
      updatePhase('entering');
      if (enterTimer !== undefined) window.clearTimeout(enterTimer);
      enterTimer = window.setTimeout(() => {
        changingRoute.current = false;
        updatePhase('ready');
      }, reducedMotion() ? 0 : 340);
    };
    const frame = requestAnimationFrame(prepare);
    const observer = new MutationObserver(prepare);
    if (scope) observer.observe(scope, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      if (enterTimer !== undefined) window.clearTimeout(enterTimer);
      observer.disconnect();
      unmark();
      sizes.disconnect();
      if (scrollingFrame !== undefined) cancelAnimationFrame(scrollingFrame);
      preview?.removeEventListener('scroll', requestMeasure);
      window.removeEventListener('resize', requestMeasure);
      frameElement.remove();
    };
  }, [active, pathname, step, updatePhase]);

  return <>
    {active && createPortal(<aside ref={panel} className="first-visit-guide first-visit-card" tabIndex={-1} aria-label="Знакомство с приложением" aria-describedby="first-visit-description" data-phase={phase}>
      <div className="first-visit-top"><span>Короткое знакомство</span><span className="first-visit-count">{currentStage + 1} / {steps.length}</span>
        <button type="button" className="first-visit-close" aria-label="Закрыть знакомство" onClick={() => finish('skipped')}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button></div>
      <div className="first-visit-progress" aria-hidden="true">{steps.map((item, index) => <i key={`${item.route}:${item.title}`} className={index <= currentStage ? 'is-done' : ''} />)}</div>
      <div className="first-visit-copy" key={`${step.route}:${step.title}`} aria-live="polite" aria-atomic="true">
        <h2>{step.title}</h2><p id="first-visit-description">{'guestText' in step && !auth.signedIn ? step.guestText : 'desktopText' in step ? <><span className="first-visit-mobile-copy">{step.text}</span><span className="first-visit-desktop-copy">{step.desktopText}</span></> : step.text}</p>
        {currentStage === 0 && <small className="first-visit-timezone">Время сессий: {timezone}</small>}
      </div>
      <div className="first-visit-actions">
        {currentStage > 0 && <button type="button" className="first-visit-secondary" disabled={phase !== 'ready'} aria-label="Назад" onClick={() => goTo(currentStage - 1)}><span className="first-visit-back-icon"><HomeIcon name="chevronRight" /></span></button>}
        <button type="button" className="first-visit-primary" disabled={phase !== 'ready'} onClick={() => currentStage === steps.length - 1 ? finish('completed') : goTo(currentStage + 1)}>
          {phase === 'leaving' || phase === 'loading' ? 'Открываем…' : currentStage === steps.length - 1 ? 'На главную' : 'Дальше'}<HomeIcon name="chevronRight" />
        </button>
      </div>
      <small className="first-visit-note">Страницу можно прокручивать и пробовать её элементы.</small>
    </aside>, document.body)}
  </>;
}
