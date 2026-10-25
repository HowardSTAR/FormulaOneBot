import { useId } from 'react';

export type TyreKind = 'hard' | 'medium' | 'soft' | 'intermediate' | 'wet';

// Original vector illustration: a slick carcass and two distinct rain tread patterns.
// No photographs, sponsor marks or external image requests.
export function TyreIllustration({ kind }: { kind: TyreKind }) {
  const id = useId().replace(/:/g, '');
  const colour = { hard: '#eeeef0', medium: '#ffcf38', soft: '#ff514e', intermediate: '#42ce77', wet: '#499aff' }[kind];
  const rain = kind === 'intermediate' || kind === 'wet';
  return <svg className="circuit-tyre-art" viewBox="0 0 160 140" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-rubber`} x1="28" y1="20" x2="106" y2="124" gradientUnits="userSpaceOnUse"><stop stopColor="#74777b" /><stop offset=".23" stopColor="#32353a" /><stop offset=".65" stopColor="#17191d" /><stop offset="1" stopColor="#080a0d" /></linearGradient>
      <radialGradient id={`${id}-wall`} cx=".35" cy=".25" r=".9"><stop stopColor="#45484e" /><stop offset=".55" stopColor="#191b20" /><stop offset="1" stopColor="#080a0d" /></radialGradient>
      <linearGradient id={`${id}-metal`} x1="94" y1="40" x2="132" y2="107" gradientUnits="userSpaceOnUse"><stop stopColor="#a9adb5" /><stop offset=".4" stopColor="#4c515b" /><stop offset="1" stopColor="#20242c" /></linearGradient>
      <clipPath id={`${id}-tread`}><path d="M74 14C45 10 24 26 21 61c-4 37 12 60 38 64l39 3c-24-8-35-31-31-62 3-28 17-47 37-49Z" /></clipPath>
    </defs>
    <ellipse cx="83" cy="130" rx="57" ry="5" fill="#080a0d" opacity=".16" />
    <path d="M74 14C45 10 24 26 21 61c-4 37 12 60 38 64l39 3c-24-8-35-31-31-62 3-28 17-47 37-49Z" fill={`url(#${id}-rubber)`} stroke="#777b84" strokeWidth=".6" />
    <g clipPath={`url(#${id}-tread)`} strokeLinecap="round">
      {rain ? <>
        {[0, 1, 2, 3, 4, 5, 6, 7, 8].map(i => <path key={i} d={`M12 ${20 + i * 14}q24 17 43 4l31 15`} stroke="#080a0d" strokeWidth={kind === 'wet' ? '4' : '2.5'} />)}
        {[39, 56].map(x => <path key={x} d={`M${x + 18} 9Q${x - 22} 57 ${x + 4} 132`} stroke="#080a0d" strokeWidth={kind === 'wet' ? '4' : '2.5'} />)}
        {kind === 'wet' && [0, 1, 2, 3, 4, 5, 6].map(i => <path key={i} d={`m25 ${33 + i * 14} 17-12m18 20 23-15`} stroke="#080a0d" strokeWidth="2" />)}
      </> : <><path d="M61 15C32 37 29 89 53 121M72 16c-28 24-29 77-7 110" stroke="#b4b7bc" strokeOpacity=".08" /><path d="M42 24c-10 16-15 35-14 55" stroke="#e3e4e6" strokeOpacity=".12" strokeWidth="2" /></>}
    </g>
    <ellipse cx="104" cy="72" rx="40" ry="56" transform="rotate(9 104 72)" fill={`url(#${id}-wall)`} stroke="#6c7079" strokeWidth=".8" />
    <ellipse cx="104" cy="72" rx="33" ry="48" transform="rotate(9 104 72)" stroke={colour} strokeWidth="2.5" />
    <ellipse cx="104" cy="72" rx="27" ry="40" transform="rotate(9 104 72)" stroke="#717782" strokeWidth="1.2" fill="#0a0d12" />
    <g transform="translate(104 72) rotate(9) scale(.66 1)">
      {Array.from({ length: 10 }, (_, i) => <path key={i} d="m-3-7-3-30 5-2L4-9Z" transform={`rotate(${i * 36})`} fill={`url(#${id}-metal)`} stroke="#9197a2" strokeWidth=".4" />)}
      <circle r="9" fill="#343a44" stroke="#88909e" strokeWidth="1.5" /><circle r="4" fill="#a5adb9" /><circle r="2" fill="#292e36" />
    </g>
    <path d="M89 29c8-4 15-4 22-1m-20 87c7 3 14 3 21-1" stroke={colour} strokeWidth="3" strokeLinecap="round" />
    <ellipse cx="104" cy="72" rx="37" ry="53" transform="rotate(9 104 72)" stroke="#e0e3e8" strokeOpacity=".08" />
  </svg>;
}
