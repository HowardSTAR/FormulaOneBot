import { useId, useRef, useState, type InputHTMLAttributes } from 'react';
import PasswordRacer from './password-racer/PasswordRacer';
import { estimatePasswordStrength } from '../helpers/passwordRacerState';
import './password-field.css';

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label: string; racer?: boolean };

export function PasswordField({ label, id, disabled, racer = false, onChange, ...props }: Props) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const input = useRef<HTMLInputElement>(null);
  const [visible, setVisible] = useState(false);
  const [inputStrength, setInputStrength] = useState(() => estimatePasswordStrength(String(props.defaultValue ?? '')));
  const strength = props.value === undefined ? inputStrength : estimatePasswordStrength(String(props.value));
  return <div className="password-field">
    {racer && <PasswordRacer passwordStrengthLevel={strength} isPasswordVisible={visible} />}
    <label htmlFor={inputId}>{label}</label>
    <div className="password-input-row">
      <input {...props} ref={input} id={inputId} disabled={disabled} type={visible ? 'text' : 'password'}
        onChange={event => {
          if (racer && props.value === undefined) setInputStrength(estimatePasswordStrength(event.currentTarget.value));
          onChange?.(event);
        }}
        spellCheck={false} autoCapitalize="none" autoCorrect="off" />
      <button type="button" disabled={disabled} aria-controls={inputId} aria-pressed={visible}
        aria-label={`${visible ? 'Скрыть пароль' : 'Показать пароль'}: ${label}`}
        onClick={() => { setVisible(value => !value); input.current?.focus({ preventScroll: true }); }}>
        {visible ? 'Скрыть' : 'Показать'}
      </button>
    </div>
  </div>;
}
