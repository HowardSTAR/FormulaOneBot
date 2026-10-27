import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ThemeToggle } from './ThemeToggle';
import './game-leaderboard-prompt.css';

type Props = {
  name: string;
  participate: boolean;
  saving: boolean;
  error: string;
  onNameChange: (name: string) => void;
  onParticipateChange: (value: boolean) => void;
  onContinue: () => void;
  onDismiss: () => void;
};

export function GameLeaderboardPrompt(props: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);

  return createPortal(<dialog ref={dialog} className="game-ranking-prompt" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`} onKeyDown={event => {
    if (event.key !== 'Tab') return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)'));
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey ? document.activeElement === first : document.activeElement === last) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  }} onCancel={event => {
    event.preventDefault();
    if (!props.saving) props.onDismiss();
  }}>
    <div className="game-ranking-tools"><ThemeToggle /><button className="game-ranking-close" type="button" aria-label="Закрыть и перейти к игре" disabled={props.saving} onClick={props.onDismiss}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div>
    <h2 id={`${id}-title`}>Таблица лидеров</h2>
    <p id={`${id}-description`}>Участвовать в рейтинге? Имя и выбор общие для всех трёх игр.</p>
    <form onSubmit={event => { event.preventDefault(); props.onContinue(); }} aria-busy={props.saving}>
      <fieldset disabled={props.saving}>
        <legend>Участие в рейтинге</legend>
        <div className="game-ranking-choices">
          {[{ value: true, label: 'Участвовать' }, { value: false, label: 'Без рейтинга' }].map(choice => <label key={choice.label}>
            <input type="radio" name="participate" checked={props.participate === choice.value} onChange={() => props.onParticipateChange(choice.value)} />
            <span>{choice.label}</span>
          </label>)}
        </div>
      </fieldset>
      <label className="game-ranking-name" htmlFor={`${id}-name`}>Имя в таблице</label>
      <input id={`${id}-name`} name="display_name" autoComplete="nickname" placeholder="Например, Alex…" maxLength={32} value={props.name} onChange={event => props.onNameChange(event.target.value)} disabled={props.saving} aria-describedby={props.error ? `${id}-error` : undefined} />
      {props.error && <p id={`${id}-error`} className="game-ranking-error" role="alert">{props.error}</p>}
      <button className="game-ranking-submit" type="submit" disabled={props.saving}>{props.saving ? 'Сохраняем…' : 'Продолжить'}</button>
    </form>
  </dialog>, document.body);
}
