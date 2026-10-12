import { useId, useRef, useState, type InputHTMLAttributes } from 'react';
import './password-field.css';

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label: string };

export function PasswordField({ label, id, disabled, ...props }: Props) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const input = useRef<HTMLInputElement>(null);
  const [visible, setVisible] = useState(false);
  return <div className="password-field">
    <label htmlFor={inputId}>{label}</label>
    <div className="password-input-row">
      <input {...props} ref={input} id={inputId} disabled={disabled} type={visible ? 'text' : 'password'}
        spellCheck={false} autoCapitalize="none" autoCorrect="off" />
      <button type="button" disabled={disabled} aria-controls={inputId} aria-pressed={visible}
        aria-label={`${visible ? 'Скрыть пароль' : 'Показать пароль'}: ${label}`}
        onClick={() => { setVisible(value => !value); input.current?.focus({ preventScroll: true }); }}>
        {visible ? 'Скрыть' : 'Показать'}
      </button>
    </div>
  </div>;
}
