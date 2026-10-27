// Keep keyboard focus in the visible game overlay, including its alternate views.
export function installMenuAccessibility() {
  const intro = document.querySelector<HTMLElement>('#race-modal')!;
  const menu = document.querySelector<HTMLElement>('#game-menu')!;
  const panel = menu.querySelector<HTMLElement>('.game-menu-panel')!;
  const gameControls = document.querySelectorAll<HTMLElement>('.hud, .touch-controls');
  let active: HTMLElement | null = null;
  let previousFocus: HTMLElement | null = null;
  const targets = (root: HTMLElement) => Array.from(root.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), [tabindex="0"]')).filter(element => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden');
  const update = () => {
    const next = menu.classList.contains('is-visible') ? panel : intro.classList.contains('is-visible') ? intro : null;
    intro.setAttribute('aria-hidden', String(next !== intro));
    gameControls.forEach(element => { element.inert = Boolean(next); });
    if (next === active) {
      if (next && document.activeElement instanceof HTMLElement && !document.activeElement.getClientRects().length) targets(next)[0]?.focus();
      return;
    }
    if (!active && next) previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    active = next;
    if (next) targets(next)[0]?.focus();
    else if (previousFocus?.isConnected) previousFocus.focus();
  };
  const observer = new MutationObserver(update);
  observer.observe(intro, { attributes: true, attributeFilter: ['class', 'hidden'], subtree: true });
  observer.observe(menu, { attributes: true, attributeFilter: ['class', 'hidden'], subtree: true });
  document.addEventListener('keydown', event => {
    if (!active || document.querySelector(':popover-open')) return;
    if (event.key === 'Escape' && active === panel) {
      event.preventDefault();
      document.querySelector<HTMLButtonElement>('#menu-close-button')?.click();
    }
    if (event.key !== 'Tab') return;
    const elements = targets(active);
    const first = elements[0], last = elements.at(-1);
    if (!active.contains(document.activeElement) || (event.shiftKey ? document.activeElement === first : document.activeElement === last)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  }, true);
  update();
}
