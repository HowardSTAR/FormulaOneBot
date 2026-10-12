import { memo } from 'react';
import type { Avatar } from './avatar';
import { avatarSprites, avatarVariants } from './avatarSprites';

/** Static, shared backgrounds: no image requests, effects or animations per choice. */
export default memo(function AvatarPortrait({ avatar, alt = '' }: { avatar: Avatar; alt?: string }) {
  return <span className="avatar-image avatar-portrait" role={alt ? 'img' : undefined}
    aria-label={alt || undefined} aria-hidden={alt ? undefined : true}
    data-helmet={avatar.helmet} data-suit={avatar.suit} data-background={avatar.background}>
    {(['background', 'suit', 'helmet'] as const).map(part => {
      const variants = avatarVariants[part];
      const index = Math.max(0, variants.indexOf(avatar[part]));
      return <span key={part} className={`avatar-portrait-${part}`} style={{
        backgroundImage: `url("${avatarSprites[part]}")`,
        backgroundSize: `${variants.length * 100}% 100%`,
        backgroundPosition: `${index * 100 / (variants.length - 1)}% 0`,
      }} />;
    })}
  </span>;
}, (previous, next) => previous.alt === next.alt
  && previous.avatar.helmet === next.avatar.helmet
  && previous.avatar.suit === next.avatar.suit
  && previous.avatar.background === next.avatar.background);
