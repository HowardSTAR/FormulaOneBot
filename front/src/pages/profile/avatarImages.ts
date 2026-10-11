import { avatarUrl, type Avatar, type AvatarOptions } from './avatar';

// The catalogue has 45 immutable portraits. Keep decoded images and share in-flight work.
const images = new Map<string, { image: HTMLImageElement; promise: Promise<void>; ready: boolean }>();
const listeners = new Set<(src: string) => void>();

export function onAvatarImageReady(listener: (src: string) => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function avatarImageReady(src: string) { return images.get(src)?.ready === true; }

export function prepareAvatarImage(src: string, priority: 'high' | 'low' = 'high'): Promise<void> {
  const cached = images.get(src);
  if (cached) {
    if (priority === 'high') cached.image.fetchPriority = 'high';
    return cached.promise;
  }
  const image = new Image();
  image.decoding = 'async';
  image.fetchPriority = priority;
  const entry = { image, ready: false, promise: Promise.resolve() };
  entry.promise = new Promise<void>((resolve, reject) => {
    let settled = false;
    const timeout = window.setTimeout(() => fail(), 15000);
    function cleanup() { window.clearTimeout(timeout); image.onload = null; image.onerror = null; }
    function fail() {
      if (settled) return;
      settled = true;
      cleanup(); images.delete(src); image.removeAttribute('src');
      reject(new Error('Не удалось загрузить образ'));
    }
    image.onerror = fail;
    image.onload = () => {
      image.decode().then(() => {
        if (settled) return;
        settled = true; cleanup(); entry.ready = true; resolve();
        listeners.forEach(listener => listener(src));
      }).catch(fail);
    };
    image.src = src;
  });
  images.set(src, entry);
  return entry.promise;
}

export function warmAvatarImages(avatar: Avatar, options: AvatarOptions) {
  let cancelled = false;
  const urls = [...new Set([avatarUrl(avatar), ...(['helmet', 'suit', 'background'] as const)
    .flatMap(key => Object.keys(options[key]).map(id => avatarUrl({ ...avatar, [key]: id })))])];
  async function worker() {
    while (!cancelled && urls.length) {
      const src = urls.shift();
      if (src) await prepareAvatarImage(src, 'low').catch(() => { /* Retry on demand in the editor. */ });
    }
  }
  const start = () => { void worker(); void worker(); };
  if ('requestIdleCallback' in window) {
    const handle = window.requestIdleCallback(start, { timeout: 1200 });
    return () => { cancelled = true; window.cancelIdleCallback(handle); };
  }
  const handle = globalThis.setTimeout(start, 150);
  return () => { cancelled = true; globalThis.clearTimeout(handle); };
}
