import { useId } from 'react';

const outline = 'm12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.2L5.8 21 7 14.2 2 9.3l6.9-1z';

export function FavoriteStar({ selected }: { selected: boolean }) {
  const id = useId();
  return <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" className="favorite-star-shape">
    <defs><linearGradient id={id} x1="0" y1="0" x2="80%" y2="100%"><stop stopColor="#fff1b0" /><stop offset=".45" stopColor="#edb84a" /><stop offset="1" stopColor="#ad6516" /></linearGradient></defs>
    <path d={outline} fill={selected ? `url(#${id})` : 'none'} stroke={selected ? '#986019' : 'currentColor'} strokeWidth="1.2" strokeLinejoin="round" />
    {selected && <><path d="M12 2v10L8.9 8.3 2 9.3l10 2.7-6.2 9 1.2-6.8 5-2.2 6.2 9-1.2-6.8L12 12l10-2.7-6.9-1z" fill="#fff6ce" opacity=".45" /><path d="m12 12 6.2 9-1.2-6.8 5-4.9z" fill="#985019" opacity=".32" /></>}
  </svg>;
}
