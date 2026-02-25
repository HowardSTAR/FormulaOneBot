import { useState, useRef, useEffect } from "react";
import { hapticSelection } from "../helpers/telegram";

export type CustomSelectOption = { value: string | number; label: string };

type CustomSelectProps = {
  options: CustomSelectOption[];
  value: string | number;
  onChange: (value: string | number) => void;
  className?: string;
  disabled?: boolean;
};

export function CustomSelect({ options, value, onChange, className = "", disabled }: CustomSelectProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => String(o.value) === String(value));
  const label = selected?.label ?? "";

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  return (
    <div
      ref={wrapperRef}
      className={`custom-select-wrapper ${open ? "open" : ""} ${className}`}
    >
      <div
        className="custom-select-trigger"
        onClick={() => !disabled && setOpen(!open)}
        role="button"
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            if (!disabled) setOpen(!open);
          }
        }}
      >
        <span>{label}</span>
        <div className="select-arrow" />
      </div>
      <div className="custom-options">
        {options.map((opt) => (
          <div
            key={String(opt.value)}
            className={`custom-option ${String(opt.value) === String(value) ? "selected" : ""}`}
            onClick={() => {
              hapticSelection();
              onChange(opt.value);
              setOpen(false);
            }}
            role="option"
            aria-selected={String(opt.value) === String(value)}
          >
            {opt.label}
          </div>
        ))}
      </div>
    </div>
  );
}
