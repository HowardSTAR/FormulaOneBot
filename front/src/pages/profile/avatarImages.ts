// Retain decoded immutable assets and share in-flight work, including sprite atlases.
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
