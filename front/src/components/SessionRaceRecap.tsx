import { RaceImpact } from './RaceImpact';
import { useRaceRecap } from '../helpers/useRaceRecap';
import type { SessionResultRow } from '../helpers/sessionClassification';

export default function SessionRaceRecap({ season, round, rows }: { season: number; round: number; rows: SessionResultRow[] }) {
  const recap = useRaceRecap(season, round, true);
  const completeRows = rows.filter((row): row is SessionResultRow & { code: string; name: string; points: number } => Boolean(row.code && row.name && typeof row.points === 'number'));
  return <details className="race-recap-fold"><summary>Обзор гонки и главные события</summary><RaceImpact season={season} round={round} rows={completeRows} recap={recap} /></details>;
}
