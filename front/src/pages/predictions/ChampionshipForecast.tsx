import { useState } from 'react';
import { HomeIcon } from '../index/HomeIcon';
import { SelectField } from '../../components/CustomSelect';
import type { PickerDriver } from '../../components/DriverPicker';
import { DriverPortrait } from '../../components/DriverPortrait';
import { TeamLogo } from '../../components/TeamLogo';
import { homeTeamIdentity } from '../index/team-identity';
import type { Candidate, ChampionshipContext, TitleAnswer, TitleAnswers } from './championship';
import './championship.css';

function Contender({ candidate, kind, season, drivers }: { candidate: Candidate; kind: 'drivers' | 'constructors'; season: number; drivers: readonly PickerDriver[] }) {
  const driver = kind === 'drivers' ? drivers.find(driver => driver.code.toUpperCase() === candidate.id.toUpperCase() || driver.name.toLocaleLowerCase() === candidate.name.toLocaleLowerCase()) : undefined;
  const code = driver?.code || (/^[A-Z]{3}$/.test(candidate.id) ? candidate.id : '');
  const team = kind === 'constructors' ? candidate.name : driver?.constructorName || '';
  return <div className="title-contender" data-team={homeTeamIdentity(kind === 'constructors' ? candidate.id : '', team)}>
    <div className="title-contender-copy"><h5>{candidate.name}</h5><p className="title-contender-points"><strong>{candidate.points.toLocaleString('ru-RU')}</strong><span>очков в чемпионате</span></p></div>
    <div className="title-contender-art" aria-hidden="true">
      {kind === 'constructors' ? <TeamLogo name={candidate.name} id={candidate.id} season={season} size={150} /> : code ? <DriverPortrait code={code} name={candidate.name} season={season} src={driver?.imageUrl} /> : <HomeIcon name="drivers" />}
    </div>
  </div>;
}

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

export function ChampionshipForecast({ context, answers, onChange, disabled = false, conditionsOnly = false, open = false, season, drivers = [] }: {
  context?: ChampionshipContext | null; answers: TitleAnswers; onChange: (answers: TitleAnswers) => void;
  disabled?: boolean; conditionsOnly?: boolean; open?: boolean;
  season?: number; drivers?: readonly PickerDriver[];
}) {
  if (!context || context.status !== 'ok' || ![...context.drivers, ...context.constructors].length) return null;
  const portraitSeason = season ?? context.season ?? new Date().getFullYear();
  return <section className="championship-forecast" aria-label="Прогноз на чемпионство">
    <div className="title-emblem" aria-hidden="true"><HomeIcon name="trophy" /></div>
    <div className="title-heading"><HomeIcon name="trophy" /><h3>Титул может решиться здесь</h3></div>
    <p className="title-scope">{context.scope || 'К концу этапа'} · могут оформить титул на этом этапе</p>
    <div className="title-candidates">{(['drivers', 'constructors'] as const).map(kind => {
      const candidates = context[kind];
      if (!candidates.length) return null;
      const selected = candidates.length === 1 ? candidates[0] : candidates.find(c => c.id === answers[kind]?.id);
      const visible = conditionsOnly ? candidates : selected ? [selected] : [];
      const change = (value: TitleAnswer) => onChange({ ...answers, [kind]: value });
      return <div className="title-candidate" key={kind}>
        <h4 className="title-category">{kind === 'drivers' ? 'Чемпион мира · пилоты' : 'Кубок конструкторов · команды'}</h4>
        {candidates.length > 1 && !conditionsOnly && <label>Выберите {kind === 'drivers' ? 'пилота' : 'команду'}
          <SelectField value={answers[kind]?.id || ''} disabled={disabled} onChange={id => change({ id, yes: null })}>
            <option value="">Выберите участника</option>
            {candidates.map(c => <option key={c.id} value={c.id}>{c.name} · {c.points} очк.</option>)}
          </SelectField>
        </label>}
        {visible.map(candidate => <div key={candidate.id}>
          <Contender candidate={candidate} kind={kind} season={portraitSeason} drivers={drivers} />
          <details open={open || undefined}><summary>Условия титула · все варианты</summary><Conditions candidate={candidate} /></details>
          {conditionsOnly ? answers[kind]?.id === candidate.id && typeof answers[kind]?.yes === 'boolean' &&
            <p className="title-saved-answer">Ваш прогноз <strong>{answers[kind]?.yes ? 'Да' : 'Нет'}</strong></p>
          : <fieldset disabled={disabled} className="title-answer"><legend>{kind === 'drivers' ? 'Станет чемпионом мира на этом этапе?' : 'Выиграет Кубок конструкторов на этом этапе?'}</legend>
            <div role="group" aria-label={kind === 'drivers' ? 'Титул пилота' : 'Титул команды'}>{([true, false] as const).map(yes => <button type="button" key={String(yes)}
              aria-pressed={answers[kind]?.yes === yes} className={answers[kind]?.yes === yes ? 'active' : ''}
              onClick={() => change({ id: candidate.id, name: candidate.name, yes })}>{yes ? 'Да' : 'Нет'}</button>)}</div>
          </fieldset>}
        </div>)}
      </div>;
    })}</div>
    <details className="title-method"><summary>Как рассчитаны условия</summary><p>{context.note}</p></details>
  </section>;
}
