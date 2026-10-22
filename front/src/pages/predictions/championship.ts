export type TitleAnswer = { id: string; yes: boolean | null; name?: string };
export type TitleAnswers = Partial<Record<'drivers' | 'constructors', TitleAnswer>>;
type Finish = { race: number[]; sprint: number[] };
type Scenario = {
  points: number;
  rivals: { id: string; name: string; points: number; max_points: number; tie_points: number | null }[];
  finishes: Finish[];
};
export type Candidate = {
  id: string; name: string; points: number; wins: number;
  remaining_points: number; future_races: number; scenarios: Scenario[]; has_sprint: boolean;
};
export type ChampionshipContext = {
  status: string; season?: number; round?: number; scope?: string; note?: string;
  drivers: Candidate[]; constructors: Candidate[];
};

export function titleAnswersComplete(context: ChampionshipContext | null | undefined, answers: TitleAnswers) {
  if (!context || context.status !== 'ok') return true;
  return (['drivers', 'constructors'] as const).every(kind => {
    const candidates = context[kind];
    const answer = answers[kind];
    return !candidates.length || (typeof answer?.yes === 'boolean' && candidates.some(c => c.id === answer.id));
  });
}
