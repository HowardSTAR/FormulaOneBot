import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { useHeroData } from '../context/useHeroData';
import { formatTimezoneLabel, getDisplayTimezone } from '../helpers/timezone';
import { ONBOARDING_CHANGED, onboardingSteps, readOnboarding, saveOnboarding } from '../helpers/onboarding';
import './first-visit-guide.css';

type Highlight = { top: number; left: number; width: number; height: number; route: string };

export function FirstVisitGuide() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { loaded, userTz } = useHeroData();
  const [stage, setStage] = useState<number | null>(() => readOnboarding() ? null : 0);
  const [started, setStarted] = useState(false);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [viewport, setViewport] = useState(() => ({ width: innerWidth, height: innerHeight, cardHeight: 280, top: 12, bottom: 12, left: 12, right: 12 }));
  const dialog = useRef<HTMLDialogElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const replay = useRef<HTMLButtonElement>(null);
  const active = stage !== null && (started || pathname === '/' && loaded);
  const step = onboardingSteps[stage ?? 0];
  const timezone = formatTimezoneLabel(getDisplayTimezone(userTz));

  useEffect(() => {
    if (!active) return;
    const node = dialog.current;
    const replayButton = replay.current;
    const previousFocus = document.activeElement;
    const overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    document.documentElement.dataset.onboardingActive = 'true';
    window.dispatchEvent(new Event(ONBOARDING_CHANGED));
    node?.showModal();
    return () => {
      node?.close();
      document.documentElement.style.overflow = overflow;
      delete document.documentElement.dataset.onboardingActive;
      window.dispatchEvent(new Event(ONBOARDING_CHANGED));
      if (previousFocus instanceof HTMLElement && previousFocus !== document.body && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
      else if (replayButton?.isConnected) replayButton.focus({ preventScroll: true });
    };
  }, [active]);

  useEffect(() => {
    if (!active) return;
    let target: HTMLElement | undefined;
    const scope = document.querySelector<HTMLElement>('.app-page-main');
    const position = () => {
      const cardHeight = card.current?.offsetHeight || 280;
      const padding = dialog.current ? getComputedStyle(dialog.current) : null;
      const top = parseFloat(padding?.paddingTop || '12'), bottom = parseFloat(padding?.paddingBottom || '12');
      const left = parseFloat(padding?.paddingLeft || '12'), right = parseFloat(padding?.paddingRight || '12');
      setViewport(previous => previous.width === innerWidth && previous.height === innerHeight && previous.cardHeight === cardHeight && previous.top === top && previous.bottom === bottom && previous.left === left && previous.right === right
        ? previous : { width: innerWidth, height: innerHeight, cardHeight, top, bottom, left, right });
      if (pathname !== step.route) { setHighlight(null); return; }
      const selector = 'target' in step ? step.target : 'h1, h2';
      const nextTarget = Array.from(scope?.querySelectorAll<HTMLElement>(selector) || []).find(node => node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden');
      if (!nextTarget) { setHighlight(null); return; }
      if (target !== nextTarget) {
        target = nextTarget;
        target.scrollIntoView({ block: 'start', behavior: 'instant' });
        window.scrollBy({ top: -top - 12, behavior: 'instant' });
      }
      const rect = target.getBoundingClientRect();
      const highlightTop = Math.max(top, rect.top - 6), highlightLeft = Math.max(left, rect.left - 6);
      setHighlight({ top: highlightTop, left: highlightLeft, width: Math.max(0, Math.min(innerWidth - right, rect.right + 6) - highlightLeft), height: Math.max(0, Math.min(innerHeight - bottom, rect.bottom + 6) - highlightTop), route: pathname });
    };
    const frame = requestAnimationFrame(position);
    card.current?.focus({ preventScroll: true });
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    const resize = new ResizeObserver(position);
    if (card.current) resize.observe(card.current);
    if (dialog.current) resize.observe(dialog.current);
    const mutations = new MutationObserver(position);
    if (scope) mutations.observe(scope, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', position);
      window.removeEventListener('scroll', position, true);
      resize.disconnect();
      mutations.disconnect();
    };
  }, [active, step, pathname]);

  const finish = (status: 'completed' | 'skipped') => {
    saveOnboarding(status);
    setStage(null);
    setStarted(false);
    if (status === 'completed') { navigate('/', { replace: true }); window.scrollTo({ top: 0, behavior: 'instant' }); }
  };
  const goTo = (index: number) => {
    setStarted(true);
    setStage(index);
    navigate(onboardingSteps[index].route, { replace: true });
  };
  const height = viewport.cardHeight;
  const width = Math.min(380, viewport.width - viewport.left - viewport.right);
  const visibleHighlight = highlight?.route === pathname && pathname === step.route ? highlight : null;
  const cardStyle = visibleHighlight ? {
    width,
    left: Math.max(viewport.left, Math.min(visibleHighlight.left, viewport.width - width - viewport.right)),
    top: visibleHighlight.top + visibleHighlight.height + height + 12 <= viewport.height - viewport.bottom
      ? visibleHighlight.top + visibleHighlight.height + 12
      : visibleHighlight.top - height - 12 >= viewport.top ? visibleHighlight.top - height - 12 : Math.max(viewport.top, Math.min((viewport.height - height) / 2, viewport.height - viewport.bottom - height)),
  } : undefined;

  return <>
    {pathname === '/' && <div className="first-visit-entry"><span>Все разделы TurboTears</span><button ref={replay} type="button" onClick={() => goTo(0)}>Короткое знакомство →</button></div>}
    {createPortal(<dialog ref={dialog} className="first-visit-dialog is-tour" aria-labelledby="first-visit-title" aria-describedby="first-visit-description"
      onCancel={event => { event.preventDefault(); finish('skipped'); }}>
      {visibleHighlight && <div className="first-visit-highlight" data-tour-route={visibleHighlight.route} aria-hidden="true" style={visibleHighlight} />}
      <div className="first-visit-card" ref={card} tabIndex={-1} style={cardStyle}>
        <div className="first-visit-top"><span>ЗНАКОМСТВО · {(stage ?? 0) + 1} / {onboardingSteps.length}</span>
          <button type="button" className="first-visit-close" aria-label="Закрыть знакомство" onClick={() => finish('skipped')}>×</button></div>
        <div className="first-visit-progress" aria-hidden="true">{onboardingSteps.map((item, index) => <i key={item.route} className={index <= (stage ?? 0) ? 'is-done' : ''} />)}</div>
        <h2 id="first-visit-title">{step.title}</h2>
        <p id="first-visit-description">{step.text}</p>
        {!visibleHighlight && <p className="first-visit-note" role="status">Открываем раздел…</p>}
        {stage === 0 && <p className="first-visit-timezone">Время сессий: {timezone}. Часовой пояс можно изменить в настройках.</p>}
        <div className="first-visit-actions">
          <button type="button" className="first-visit-secondary" onClick={() => finish('skipped')}>Пропустить</button>
          {(stage ?? 0) > 0 && <button type="button" className="first-visit-secondary" aria-label="Назад" onClick={() => goTo((stage ?? 0) - 1)}><span aria-hidden="true">←</span></button>}
          <button type="button" className="first-visit-primary" disabled={!visibleHighlight} onClick={() => stage === onboardingSteps.length - 1 ? finish('completed') : goTo((stage ?? 0) + 1)}>
            {stage === onboardingSteps.length - 1 ? 'На главную →' : 'Дальше →'}
          </button>
        </div>
        {stage === 0 && <small className="first-visit-note">Один маршрут по главным разделам. Можно пропустить и повторить на главной.</small>}
      </div>
    </dialog>, document.body)}
  </>;
}
