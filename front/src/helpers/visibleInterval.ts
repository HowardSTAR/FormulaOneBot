type VisibilityRuntime = {
  document: Pick<Document, 'hidden' | 'addEventListener' | 'removeEventListener'>;
  setInterval: (tick: () => void, delay: number) => number;
  clearInterval: (timer: number) => void;
};

/** Stop background-tab work; catch up once as soon as the tab is visible. */
export function visibleInterval(tick: () => void, delay: number, runtime: VisibilityRuntime = {
  document,
  setInterval: window.setInterval.bind(window),
  clearInterval: window.clearInterval.bind(window),
}): () => void {
  let timer: number | undefined;
  const stop = () => {
    if (timer !== undefined) runtime.clearInterval(timer);
    timer = undefined;
  };
  const start = () => {
    if (!runtime.document.hidden) timer = runtime.setInterval(tick, delay);
  };
  const changed = () => {
    stop();
    if (!runtime.document.hidden) {
      tick();
      start();
    }
  };
  runtime.document.addEventListener('visibilitychange', changed);
  start();
  return () => {
    stop();
    runtime.document.removeEventListener('visibilitychange', changed);
  };
}
