export const TROPHY_CHECK = 'turbotears:trophy-check';
export const TROPHY_UPDATED = 'turbotears:trophy-updated';
export const TROPHY_BADGE_CHANGED = 'turbotears:trophy-badge-changed';
export type TrophyAward = { id: string; family: string; season: number; level: number; name: string; tier: string; earned_at: string };
export type TrophyLevel = { id: string; level: number; tier: string; season: number; earned_at: string | null; target?: number | null; progress?: number; condition?: string; rule?: string };
export type TrophyFamily = { id: string; name: string; group: string; levels: TrophyLevel[] };
export type TrophyCollection = { user_id: number; season: number; calendar_known: boolean; season_closed: boolean; families: TrophyFamily[]; earned: TrophyAward[]; pending: TrophyAward[]; badge: TrophyAward | null };
export const trophyImage = (family: string, level: number) => `/images/trophies/${family}-${['bronze','silver','gold'][level]}.webp`;

export function mergeTrophyQueue(pending: TrophyAward[], dismissed: Set<string>): TrophyAward[] {
  return pending.filter((award, index) => !dismissed.has(award.id) && pending.findIndex(other => other.id === award.id) === index);
}
