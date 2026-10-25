import { useEffect, useEffectEvent, useLayoutEffect, useRef } from 'react';

/** Native paging with inert visual buffers: crossing an edge travels one page. */
export function useCircularSpotlight(count: number, active: number, wide: boolean, onSelect: (index: number) => void) {
  const viewport = useRef<HTMLDivElement>(null);
  const current = useRef(active);
  const destination = useRef<number | null>(null);
  const layout = useRef({ count: 0, wide, width: 0 });
  const publish = useEffectEvent((index: number) => {
    if (index !== current.current) { current.current = index; onSelect(index); }
  });
  const copyEdges = () => {
    const node = viewport.current;
    if (!node) return;
    const slides = node.querySelectorAll<HTMLElement>(':scope > .home-spotlight-slide');
    const buffers = node.querySelectorAll<HTMLElement>(':scope > .home-spotlight-buffer');
    [slides[slides.length - 1], slides[0]].forEach((slide, index) => {
      if (!slide || !buffers[index]) return;
      const visual = slide.cloneNode(true) as HTMLElement;
      visual.className = 'home-spotlight-snapshot';
      visual.removeAttribute('data-slide-index');
      visual.removeAttribute('inert');
      visual.querySelectorAll('[id], [aria-labelledby], [aria-describedby]').forEach(element => {
        element.removeAttribute('id'); element.removeAttribute('aria-labelledby'); element.removeAttribute('aria-describedby');
      });
      buffers[index].replaceChildren(visual);
    });
  };
  useLayoutEffect(() => {
    copyEdges();
    const node = viewport.current;
    if (!node) return;
    const width = node.getBoundingClientRect().width;
    const changed = layout.current.count !== count || layout.current.wide !== wide;
    if (!wide && (changed || active !== current.current)) {
      current.current = active;
      destination.current = active + 1;
      node.scrollTo({ left: width * (active + 1), behavior: 'instant' });
    }
    layout.current = { count, wide, width };
  });
  const select = (index: number) => {
    const node = viewport.current;
    if (!node || wide) return;
    const next = (index + count) % count;
    if (Math.abs(next - current.current) === count - 1) copyEdges();
    const page = next === 0 && current.current === count - 1 ? count + 1
      : next === count - 1 && current.current === 0 ? 0 : next + 1;
    destination.current = page;
    node.scrollTo({ left: page * layout.current.width, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  };
  const selectFromWheel = useEffectEvent((index: number) => select(index));
  useEffect(() => {
    const node = viewport.current;
    if (!node || wide) return;
    let settling: ReturnType<typeof setTimeout> | undefined;
    const settle = () => {
      const width = layout.current.width;
      if (!width || layout.current.wide) return;
      const total = layout.current.count;
      if (destination.current !== null && Math.abs(node.scrollLeft - destination.current * width) > 2) {
        // An old scrollend can arrive after a new gesture has started.
        // Never finish that new animation on behalf of the previous one.
        return;
      }
      destination.current = null;
      const page = Math.round(node.scrollLeft / width);
      const index = ((page - 1) % total + total) % total;
      publish(index);
      if (page === 0 || page === total + 1) node.scrollTo({ left: (index + 1) * width, behavior: 'instant' });
    };
    const onScroll = () => {
      if (layout.current.wide) return;
      const total = layout.current.count;
      const width = layout.current.width;
      if (!width) return;
      const page = Math.round(node.scrollLeft / width);
      if (destination.current === null || Math.abs(node.scrollLeft - destination.current * width) <= 2) {
        destination.current = null;
        publish(((page - 1) % total + total) % total);
      }
      clearTimeout(settling); settling = setTimeout(settle, 160);
    };
    let wheel = { time: -Infinity, distance: 0, direction: 0, moved: false };
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
      event.preventDefault();
      const direction = Math.sign(event.deltaX);
      if (event.timeStamp - wheel.time > 180 || wheel.direction !== direction) wheel = { time: event.timeStamp, distance: 0, direction, moved: false };
      wheel.time = event.timeStamp;
      wheel.distance += Math.abs(event.deltaX) * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? layout.current.width : 1);
      if (!wheel.moved && wheel.distance >= 50) { wheel.moved = true; selectFromWheel(current.current + direction); }
    };
    const resize = new ResizeObserver(() => {
      const width = node.getBoundingClientRect().width;
      if (width !== layout.current.width) {
        layout.current.width = width;
        node.scrollTo({ left: (current.current + 1) * width, behavior: 'instant' });
      }
    });
    const media = (event: Event) => {
      if (destination.current === null && !(event.target as Element).closest('.home-spotlight-buffer')) {
        const left = node.scrollLeft;
        copyEdges();
        node.scrollLeft = left;
      }
    };
    resize.observe(node);
    node.addEventListener('scroll', onScroll, { passive: true });
    node.addEventListener('scrollend', settle);
    node.addEventListener('wheel', onWheel, { passive: false });
    const interrupt = () => { destination.current = null; copyEdges(); };
    node.addEventListener('touchstart', interrupt, { passive: true });
    node.addEventListener('load', media, true); node.addEventListener('error', media, true);
    return () => {
      clearTimeout(settling); resize.disconnect(); node.removeEventListener('scroll', onScroll); node.removeEventListener('scrollend', settle);
      node.removeEventListener('wheel', onWheel); node.removeEventListener('load', media, true); node.removeEventListener('error', media, true);
      node.removeEventListener('touchstart', interrupt);
    };
  }, [count, wide]);
  return { viewport, select };
}
