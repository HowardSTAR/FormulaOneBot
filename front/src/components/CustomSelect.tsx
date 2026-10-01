import { hapticSelection } from "../helpers/telegram";

export type CustomSelectOption = { value: string | number; label: string };

type CustomSelectProps = {
  options: CustomSelectOption[];
  value: string | number;
  onChange: (value: string | number) => void;
  className?: string;
  disabled?: boolean;
  ariaLabel?: string;
};

/** Native selection supports arrows, Enter, Escape, touch and screen readers. */
export function CustomSelect({ options, value, onChange, className = "", disabled, ariaLabel = "Выберите значение" }: CustomSelectProps) {
  return <div className={`custom-select-wrapper ${className}`}>
    <select className="custom-select-native" value={String(value)} disabled={disabled} aria-label={ariaLabel}
      onChange={event => {
        const option = options.find(item => String(item.value) === event.target.value);
        if (option) { hapticSelection(); onChange(option.value); }
      }}>
      {options.map(option => <option key={String(option.value)} value={String(option.value)}>{option.label}</option>)}
    </select>
  </div>;
}
