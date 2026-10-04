import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { formatTimezoneLabel } from '../helpers/timezone';
import { ONBOARDING_CHANGED, onboardingGoals, readOnboarding, saveOnboarding, type OnboardingGoal } from '../helpers/onboarding';
import './first-visit-guide.css';

const steps = [
  { target: '[data-onboarding="schedule"]', title: 'Когда следующая сессия?', text: 'В расписании — практики, квалификация и гонка. Нажмите на сессию, чтобы открыть этап. «Весь сезон» ведёт в календарь.' },
  { target: '[data-onboarding="predictions"]', title: 'Ваш первый прогноз', text: 'Здесь вход в прогнозы. В разделе показаны срок приёма и правила начисления очков. Для сохранения прогноза понадобится аккаунт.' },
  { target: '[data-onboarding="results"]', title: 'Что произошло на трассе?', text: 'Откройте результаты и выберите нужную сессию. Рядом в быстром доступе — сравнение пилотов и справочник с объяснением терминов F1.' },
];
type Highlight = { top: number; left: number; width: number; height: number };

export function FirstVisitGuide({ ready, timezone }: { ready: boolean; timezone: string }) {
  const navigate = useNavigate();
  const [stage, setStage] = useState<number | null>(() => readOnboarding() ? null : -1);
  const [goal, setGoal] = useState<OnboardingGoal>(() => readOnboarding()?.goal || 'schedule');
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [viewport, setViewport] = useState(() => ({ width: innerWidth, height: innerHeight, cardHeight: 280 }));
  const dialog = useRef<HTMLDialogElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const replay = useRef<HTMLButtonElement>(null);
  const active = ready && stage !== null;
  const selected = onboardingGoals.find(item => item.id === goal)!;
  const step = stage !== null && stage >= 0 ? steps[stage] : null;

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
      else replayButton?.focus({ preventScroll: true });
    };
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const target = step ? document.querySelector<HTMLElement>(step.target) : null;
    const position = () => {
      const cardHeight = card.current?.offsetHeight || 280;
      setViewport(previous => previous.width === innerWidth && previous.height === innerHeight && previous.cardHeight === cardHeight
        ? previous : { width: innerWidth, height: innerHeight, cardHeight });
      if (!target || !target.getClientRects().length) { setHighlight(null); return; }
      const rect = target.getBoundingClientRect();
      const top = Math.max(8, rect.top - 6), left = Math.max(8, rect.left - 6);
      setHighlight({ top, left, width: Math.max(0, Math.min(innerWidth - 8, rect.right + 6) - left), height: Math.max(0, Math.min(innerHeight - 8, rect.bottom + 6) - top) });
    };
    target?.scrollIntoView({ block: 'start', behavior: 'instant' });
    if (target) window.scrollBy({ top: -24, behavior: 'instant' });
    const frame = requestAnimationFrame(position);
    card.current?.focus({ preventScroll: true });
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    const observer = new ResizeObserver(position);
    if (target) observer.observe(target);
    if (card.current) observer.observe(card.current);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', position);
      window.removeEventListener('scroll', position, true);
      observer.disconnect();
    };
  }, [active, step]);

  const finish = (status: 'completed' | 'skipped', destination?: string) => {
    saveOnboarding(status, goal);
    setStage(null);
    if (destination) navigate(destination);
  };
  // Place the tip beside its highlighted control, or centrally on short screens.
  const height = viewport.cardHeight;
  const width = Math.min(380, viewport.width - 24);
  const cardStyle = step && highlight ? {
    left: Math.max(12, Math.min(highlight.left, viewport.width - width - 12)),
    top: highlight.top + highlight.height + height + 24 <= viewport.height
      ? highlight.top + highlight.height + 12
      : highlight.top - height - 12 >= 12 ? highlight.top - height - 12 : Math.max(12, (viewport.height - height) / 2),
  } : undefined;

  return <>
    <div className="first-visit-entry"><span>Первый раз в TurboTears?</span><button ref={replay} type="button" onClick={() => setStage(-1)}>Короткое знакомство →</button></div>
    {createPortal(<dialog ref={dialog} className={`first-visit-dialog${step ? ' is-tour' : ''}`} aria-labelledby="first-visit-title" aria-describedby="first-visit-description"
      onCancel={event => { event.preventDefault(); finish('skipped'); }}>
      {step && highlight && <div className="first-visit-highlight" aria-hidden="true" style={highlight} />}
      <div className="first-visit-card" ref={card} tabIndex={-1} style={cardStyle}>
        <div className="first-visit-top"><span>{step ? `ПОДСКАЗКА ${(stage ?? 0) + 1} / ${steps.length}` : 'БЫСТРЫЙ СТАРТ · TURBOTEARS'}</span>
          <button type="button" className="first-visit-close" aria-label="Закрыть знакомство" onClick={() => finish('skipped')}>×</button></div>
        <h2 id="first-visit-title">{step?.title || 'Ваш уик-энд начинается здесь'}</h2>
        <p id="first-visit-description">{step?.text || 'Что вам интереснее? Выберите первый шаг — покажем, где его найти.'}</p>
        {!step && <>
          <fieldset className="first-visit-goals"><legend>С чего начнём?</legend>{onboardingGoals.map(item => <label key={item.id} className={goal === item.id ? 'is-selected' : ''}>
            <input type="radio" name="onboarding-goal" value={item.id} checked={goal === item.id} onChange={() => setGoal(item.id)} />
            <span className="first-visit-icon" aria-hidden="true">{item.icon}</span><span><strong>{item.title}</strong><small>{item.description}</small></span>
          </label>)}</fieldset>
          <p className="first-visit-timezone">Время сессий: <strong>{formatTimezoneLabel(timezone)}</strong>. Используем ваш часовой пояс; изменить его можно в настройках после входа.</p>
        </>}
        {step && stage === 0 && <p className="first-visit-timezone">На этой странице время показано в {formatTimezoneLabel(timezone)}.</p>}
        <div className="first-visit-actions">
          <button type="button" className="first-visit-secondary" onClick={() => finish('skipped')}>Пропустить</button>
          {step && <button type="button" className="first-visit-secondary" onClick={() => setStage(value => (value ?? 0) - 1)}>Назад</button>}
          <button type="button" className="first-visit-primary" onClick={() => stage === steps.length - 1 ? finish('completed', selected.route) : setStage(value => (value ?? -1) + 1)}>
            {!step ? 'Показать, где что' : stage === steps.length - 1 ? selected.action : 'Дальше →'}
          </button>
        </div>
        {!step && <small className="first-visit-note">Три подсказки · можно пропустить и повторить на главной</small>}
      </div>
    </dialog>, document.body)}
  </>;
}
