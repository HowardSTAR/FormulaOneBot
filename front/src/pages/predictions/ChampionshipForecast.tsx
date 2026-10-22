import { useState } from 'react';
import { SelectField } from '../../components/CustomSelect';
import './championship.css';

export type TitleAnswer = { id: string; yes: boolean | null; name?: string };
export type TitleAnswers = Partial<Record<'drivers' | 'constructors', TitleAnswer>>;
type Finish = { race: number[]; sprint: number[] };
type Scenario = { points: number; rivals: { id: string; name: string; points: number; max_points: number; tie_points: number | null }[]; finishes: Finish[] };
type Candidate = { id: string; name: string; points: number; wins: number; remaining_points: number; future_races: number; scenarios: Scenario[]; has_sprint: boolean };
export type ChampionshipContext = { status: string; season?: number; round?: number; scope?: string; note?: string; drivers: Candidate[]; constructors: Candidate[] };

function places(values: number[]) {
  return values.map(p => p ? `P${p}` : 'без классификации').join(' + ');
}

function Conditions({ candidate }: { candidate: Candidate }) {
  const [active, setActive] = useState(0);
  const [limit, setLimit] = useState(20);
  const scenario = candidate.scenarios[active] || candidate.scenarios[0];
  if (!scenario) return null;
  return <div className="title-conditions">
    <p>После этого этапа соперник сможет набрать ещё до <strong>{candidate.remaining_points} очк.</strong> Проверены все соперники. Все ограничения ниже должны выполняться одновременно.</p>
    <label>Очки {candidate.has_sprint ? 'за гонку и спринт вместе' : 'за гонку'}
      <SelectField value={active} onChange={e => { setActive(Number(e)); setLimit(20); }}>
        {candidate.scenarios.map((s, index) => <option key={s.points} value={index}>Набрать {s.points} очк.</option>)}
      </SelectField>
    </label>
    {!scenario.rivals.length && <p className="title-guarantee">Титул независимо от очков соперников.</p>}
    <ul aria-label="Условия по соперникам">{scenario.rivals.map(r => <li key={r.id}><strong>{r.name}</strong> · сейчас {r.points} очк.<br />
      {r.max_points >= 0 ? <>Набрать не более <b>{r.max_points} очк.</b></> : 'Только равенство с преимуществом по местам.'}
      {r.tie_points !== null && r.max_points >= 0 && <span className="title-tie">При {r.tie_points} очк. нужен выигрыш по дополнительным показателям.</span>}
    </li>)}</ul>
    {scenario.rivals.some(r => r.tie_points !== null) && <details><summary>Как решается равенство очков</summary><p>Нужно сохранить преимущество по победам, затем вторым, третьим и следующим местам, даже если соперник выиграет все оставшиеся гонки. В сезоне 2026 при полном равенстве сравниваются квалификации.</p></details>}
    <details><summary>Места, дающие {scenario.points} очк. ({scenario.finishes.length})</summary>
      <ul className="title-finishes">{scenario.finishes.slice(0, limit).map((f, index) => <li key={index}>Гонка: {places(f.race)}{f.sprint.length > 0 && <> · Спринт: {places(f.sprint)}</>}</li>)}</ul>
      {limit < scenario.finishes.length && <button type="button" onClick={() => setLimit(n => n + 40)}>Показать ещё варианты</button>}
    </details>
  </div>;
}

export function ChampionshipForecast({ context, answers, onChange, disabled = false, conditionsOnly = false, open = false }: {
  context?: ChampionshipContext | null; answers: TitleAnswers; onChange: (answers: TitleAnswers) => void;
  disabled?: boolean; conditionsOnly?: boolean; open?: boolean;
}) {
  if (!context || context.status !== 'ok' || ![...context.drivers, ...context.constructors].length) return null;
  return <section className="championship-forecast" aria-label="Прогноз на чемпионство">
    <div className="title-heading"><span>🏆</span><div><small>МАТЕМАТИКА ТИТУЛА</small><h3>Титул может решиться здесь</h3></div></div>
    <p className="title-scope">{context.scope || 'К концу этапа'} · могут оформить титул на этом этапе</p>
    {(['drivers', 'constructors'] as const).map(kind => {
      const candidates = context[kind];
      if (!candidates.length) return null;
      const selected = candidates.length === 1 ? candidates[0] : candidates.find(c => c.id === answers[kind]?.id);
      const change = (value: TitleAnswer) => onChange({ ...answers, [kind]: value });
      return <div className="title-candidate" key={kind}>
        <span className="title-category">{kind === 'drivers' ? 'Чемпион мира · пилоты' : 'Кубок конструкторов · команды'}</span>
        {candidates.length > 1 && !conditionsOnly && <label>Выберите {kind === 'drivers' ? 'пилота' : 'команду'}
          <SelectField value={answers[kind]?.id || ''} disabled={disabled} onChange={id => change({ id, yes: null })}>
            <option value="">Выберите участника</option>
            {candidates.map(c => <option key={c.id} value={c.id}>{c.name} · {c.points} очк.</option>)}
          </SelectField>
        </label>}
        {conditionsOnly ? candidates.map(c => <div key={c.id}><details open={open || undefined}><summary>{c.name} · {c.points} очк.</summary><Conditions candidate={c} /></details>
          {answers[kind]?.id === c.id && typeof answers[kind]?.yes === 'boolean' && <p>Ваш прогноз: <strong>{answers[kind]?.yes ? 'Да' : 'Нет'}</strong></p>}
        </div>) : selected && <>
          <div className="title-candidate-name"><strong>{selected.name}</strong><span>{selected.points} очк. в чемпионате</span></div>
          <details open={open || undefined}><summary>Условия титула · все варианты</summary><Conditions key={selected.id} candidate={selected} /></details>
          <fieldset disabled={disabled} className="title-answer"><legend>{kind === 'drivers' ? 'Станет чемпионом мира на этом этапе?' : 'Выиграет Кубок конструкторов на этом этапе?'}</legend>
            <div role="group" aria-label={kind === 'drivers' ? 'Титул пилота' : 'Титул команды'}>{([true, false] as const).map(yes => <button type="button" key={String(yes)}
              aria-pressed={answers[kind]?.yes === yes} className={answers[kind]?.yes === yes ? 'active' : ''}
              onClick={() => change({ id: selected.id, name: selected.name, yes })}>{yes ? 'Да' : 'Нет'}</button>)}</div>
          </fieldset>
        </>}
      </div>;
    })}
    <details className="title-method"><summary>Как рассчитаны условия</summary><p>{context.note}</p></details>
  </section>;
}

export function titleAnswersComplete(context: ChampionshipContext | null | undefined, answers: TitleAnswers) {
  if (!context || context.status !== 'ok') return true;
  return (['drivers', 'constructors'] as const).every(kind => !context[kind].length ||
    (typeof answers[kind]?.yes === 'boolean' && context[kind].some(c => c.id === answers[kind]?.id)));
}
