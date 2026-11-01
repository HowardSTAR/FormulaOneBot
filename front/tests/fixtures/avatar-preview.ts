// Local-only composition of the same atlases used by the profile editor.
import { avatarSprites, avatarVariants } from '../../src/pages/profile/avatarSprites';

const images = Object.fromEntries(Object.entries(avatarSprites).map(([part, src]) => {
  const image = new Image(); image.src = src;
  return [part, image];
})) as Record<keyof typeof avatarSprites, HTMLImageElement>;
const cache = new Map<string, Promise<string>>();

export function previewAvatar(source: string): Promise<string> {
  const params = new URL(source).searchParams;
  const selection = Object.fromEntries(Object.entries(avatarVariants).map(([part, variants]) => [part, Math.max(0, variants.indexOf(params.get(part) || ''))])) as Record<keyof typeof avatarSprites, number>;
  const key = JSON.stringify(selection);
  if (!cache.has(key)) cache.set(key, (async () => {
    await Promise.all(Object.values(images).map(image => image.decode()));
    const canvas = document.createElement('canvas'); canvas.width = 384; canvas.height = 384;
    const context = canvas.getContext('2d')!;
    for (const part of ['background', 'suit', 'helmet'] as const) {
      const image = images[part];
      const width = image.naturalWidth / avatarVariants[part].length;
      const height = part === 'background' ? 384 : part === 'suit' ? 146 : 238;
      context.drawImage(image, width * selection[part], 0, width, image.naturalHeight, 0, part === 'suit' ? 238 : 0, 384, height);
    }
    return canvas.toDataURL('image/png');
  })());
  return cache.get(key)!;
}
