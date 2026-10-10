import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
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
  const { loaded, userTz } = useHeroData();
  const [stage, setStage] = useState<number | null>(() => readOnboarding() ? null : 0);
  const [started, setStarted] = useState(false);
  const [phase, setPhase] = useState<Phase>('loading');
  const phaseRef = useRef<Phase>('loading');
  const changingRoute = useRef(false);
  const changeTimer = useRef<number | null>(null);
  const panel = useRef<HTMLElement>(null);
  const active = stage !== null && (started || pathname === '/' && loaded);
  const step = onboardingSteps[stage ?? 0];
  const timezone = formatTimezoneLabel(getDisplayTimezone(userTz));
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
      navigate(onboardingSteps[0].route, { replace: true });
    };
    window.addEventListener(ONBOARDING_START, start);
    return () => window.removeEventListener(ONBOARDING_START, start);
  }, [navigate, updatePhase]);

  const goTo = (index: number) => {
    if (!active) {
      setStarted(true);
      setStage(index);
      updatePhase('loading');
      navigate(onboardingSteps[index].route, { replace: true });
      return;
    }
    if (phaseRef.current !== 'ready') return;
    setStarted(true);
    changingRoute.current = true;
    updatePhase('leaving');
    changeTimer.current = window.setTimeout(() => {
      setStage(index);
      updatePhase('loading');
      navigate(onboardingSteps[index].route, { replace: true });
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
    const index = onboardingSteps.findIndex(item => item.route === pathname);
    const frame = requestAnimationFrame(() => {
      if (index < 0) finish('skipped');
      else { setStage(index); updatePhase('loading'); }
    });
    return () => cancelAnimationFrame(frame);
  }, [active, pathname, step.route, finish, updatePhase]);

  useEffect(() => {
    if (!active || pathname !== step.route) return;
    const preview = document.querySelector<HTMLElement>('.app-content');
    const scope = document.querySelector<HTMLElement>('.app-page-main');
    let target: HTMLElement | undefined;
    let prepared = false;
    let enterTimer: number | undefined;
    const unmark = () => {
      target?.classList.remove('first-visit-highlight');
      if (target) delete target.dataset.tourRoute;
    };
    const prepare = () => {
      if (!preview || !scope || scope.querySelector('.route-loading')) return;
      const visible = (node: HTMLElement) => node.getBoundingClientRect().height > 0 && getComputedStyle(node).visibility !== 'hidden';
      const candidate = Array.from(scope.querySelectorAll<HTMLElement>(step.target)).find(visible)
        || Array.from(scope.querySelectorAll<HTMLElement>('h1, h2')).find(visible);
      if (!candidate) return;
      if (candidate !== target) {
        unmark();
        target = candidate;
        target.classList.add('first-visit-highlight');
        target.dataset.tourRoute = step.route;
      }
      if (prepared) return;
      prepared = true;
      preview.scrollTo({ top: 0, behavior: 'instant' });
      const rect = target.getBoundingClientRect();
      const targetTop = rect.top - preview.getBoundingClientRect().top;
      // Keep the heading and surrounding context when the control is already
      // visible. Only bring deeper sections to the top of the workspace.
      const top = rect.height > preview.clientHeight * .5
        ? Math.max(0, targetTop - 20)
        : Math.max(0, targetTop + rect.height - preview.clientHeight + 20);
      preview.scrollTo({ top, behavior: reducedMotion() ? 'instant' : 'smooth' });
      updatePhase('entering');
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
    };
  }, [active, pathname, step, updatePhase]);

  return <>
    {active && createPortal(<aside ref={panel} className="first-visit-guide first-visit-card" tabIndex={-1} aria-label="Знакомство с приложением" aria-describedby="first-visit-description" data-phase={phase}>
      <div className="first-visit-top"><span>ЗНАКОМСТВО · {(stage ?? 0) + 1} / {onboardingSteps.length}</span>
        <button type="button" className="first-visit-close" aria-label="Закрыть знакомство" onClick={() => finish('skipped')}>×</button></div>
      <div className="first-visit-progress" aria-hidden="true">{onboardingSteps.map((item, index) => <i key={item.route} className={index <= (stage ?? 0) ? 'is-done' : ''} />)}</div>
      <div className="first-visit-copy" key={step.route} aria-live="polite" aria-atomic="true">
        <h2>{step.title}</h2><p id="first-visit-description">{step.text}</p>
        {stage === 0 && <small className="first-visit-timezone">Время сессий: {timezone}</small>}
      </div>
      <div className="first-visit-actions">
        <button type="button" className="first-visit-secondary" onClick={() => finish('skipped')}>Пропустить</button>
        {(stage ?? 0) > 0 && <button type="button" className="first-visit-secondary" disabled={phase !== 'ready'} aria-label="Назад" onClick={() => goTo((stage ?? 0) - 1)}><span aria-hidden="true">←</span></button>}
        <button type="button" className="first-visit-primary" disabled={phase !== 'ready'} onClick={() => stage === onboardingSteps.length - 1 ? finish('completed') : goTo((stage ?? 0) + 1)}>
          {phase === 'leaving' || phase === 'loading' ? 'Открываем…' : stage === onboardingSteps.length - 1 ? 'На главную →' : 'Дальше →'}
        </button>
      </div>
      <small className="first-visit-note">Страницу можно прокручивать и пробовать её элементы.</small>
    </aside>, document.body)}
  </>;
}
