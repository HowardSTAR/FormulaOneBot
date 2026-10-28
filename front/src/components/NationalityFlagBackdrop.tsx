import { getFlagCodeForNationality } from '../constants/flags';
import { FlagBackdrop } from './FlagBackdrop';

/** Entrant nationality is independent of the venue and the team's ownership. */
export function NationalityFlagBackdrop({ nationality }: { nationality: string }) {
  return <FlagBackdrop code={getFlagCodeForNationality(nationality)} className="entrant-flag-backdrop" />;
}
