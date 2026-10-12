import helmet from '../../assets/avatar/helmet-v1.webp';
import suit from '../../assets/avatar/suit-v1.webp';
import background from '../../assets/avatar/background-v1.webp';
import { avatarImageReady, prepareAvatarImage } from './avatarImages';

// Three decoded atlases cover every combination. Selection never fetches an image.
export const avatarSprites = { helmet, suit, background };
export const avatarVariants = {
  helmet: ['scarlet', 'cobalt', 'mint'],
  suit: ['scarlet', 'cobalt', 'mint'],
  background: ['garage', 'scarlet', 'cobalt', 'mint', 'gold'],
};
export function avatarSpritesReady() {
  return Object.values(avatarSprites).every(avatarImageReady);
}
export async function prepareAvatarSprites(priority: 'high' | 'low' = 'high') {
  // Settle the whole attempt before offering retry, including partial failures.
  const results = await Promise.allSettled(Object.values(avatarSprites).map(src => prepareAvatarImage(src, priority)));
  const failed = results.find(result => result.status === 'rejected');
  if (failed?.status === 'rejected') throw failed.reason;
}

export function warmAvatarSprites() {
  const start = () => { void prepareAvatarSprites('low').catch(() => { /* Retry in the editor. */ }); };
  if ('requestIdleCallback' in window) {
    const handle = window.requestIdleCallback(start, { timeout: 1200 });
    return () => window.cancelIdleCallback(handle);
  }
  const handle = globalThis.setTimeout(start, 150);
  return () => globalThis.clearTimeout(handle);
}
