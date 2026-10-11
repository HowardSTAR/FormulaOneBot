import { useEffect, useState } from 'react';
import { avatarImageReady, onAvatarImageReady, prepareAvatarImage } from './avatarImages';

/** Keep the last decoded portrait visible while the next selection loads. */
export default function AvatarImage({ src, alt = '' }: { src: string; alt?: string }) {
  const [layers, setLayers] = useState(() => avatarImageReady(src) ? [{ src, id: 0 }] : []);
  const [failed, setFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const current = layers.at(-1);
  const pending = current?.src !== src && failed !== src;
  useEffect(() => {
    let active = true;
    const show = () => {
      if (active) {
        setFailed(null);
        setLayers(previous => previous.at(-1)?.src === src ? previous : [...previous, { src, id: (previous.at(-1)?.id ?? 0) + 1 }]);
      }
    };
    const unsubscribe = onAvatarImageReady(ready => { if (ready === src) show(); });
    prepareAvatarImage(src, alt ? 'high' : 'low').then(show).catch(() => { if (active) setFailed(src); });
    return () => { active = false; unsubscribe(); };
  }, [src, alt, attempt]);
  useEffect(() => {
    // Also release old layers when animations are disabled or the tab is in the background.
    const handle = window.setTimeout(() => setLayers(previous => previous.length > 1 ? previous.slice(-1) : previous), 300);
    return () => window.clearTimeout(handle);
  }, [current?.id]);
  return <span className="avatar-image" aria-busy={pending} data-pending={pending}>
    {layers.map(layer => <img key={layer.id} src={layer.src} width="384" height="384"
      alt={layer === current ? alt : ''} aria-hidden={layer !== current || !alt ? true : undefined}
      className={layer.id ? 'avatar-image-arrive' : undefined} />)}
    {!current && <span className="avatar-image-placeholder" aria-hidden="true">TT</span>}
    {alt && pending && <span className="avatar-image-status" role="status">Загружаем образ…</span>}
    {alt && failed === src && <button type="button" className="avatar-image-retry" onClick={() => { setFailed(null); setAttempt(value => value + 1); }}>Образ не загрузился · Повторить</button>}
  </span>;
}
