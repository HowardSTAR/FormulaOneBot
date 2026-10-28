import { raceCountryCode } from '../helpers/raceCountry';
import { FlagBackdrop } from './FlagBackdrop';

/** Decorative only: the surrounding heading remains the source of event identity. */
export function RaceFlagBackdrop({ country, eventName, className }: {
  country?: string; eventName?: string; className?: string;
}) {
  return <FlagBackdrop code={raceCountryCode(country, eventName)} className={className} />;
}
