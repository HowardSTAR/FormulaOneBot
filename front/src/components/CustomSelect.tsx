import { Children, isValidElement, useId, useLayoutEffect, useRef, useState, type ReactNode, type ReactElement } from 'react';
import { hapticSelection } from '../helpers/telegram';
import { trackAction } from '../helpers/analytics';
import './custom-select.css';

export type CustomSelectOption = { value: string | number; label: string; disabled?: boolean };
type CustomSelectProps = {
  options: CustomSelectOption[]; value: string | number; onChange: (value: string | number) => void;
  className?: string; disabled?: boolean; ariaLabel?: string; id?: string;
};

/** A single branded listbox for touch, mouse and keyboard selection. */
export function CustomSelect({options, value, onChange, className = '', disabled = false, ariaLabel, id}: CustomSelectProps) {
  const listId = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const anchor = useRef({top: 0, left: 0});
  const search = useRef({text: '', time: 0});
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const label = ariaLabel || 'Выберите значение';
  const selected = options.findIndex(option => String(option.value) === String(value));
  useLayoutEffect(() => {
    if (ariaLabel) return;
    const parent = wrapper.current?.closest('label');
    const text = parent && Array.from(parent.childNodes).filter(node => node !== wrapper.current).map(node => node.textContent).join(' ').trim();
    trigger.current?.setAttribute('aria-label', text || 'Выберите значение');
    menu.current?.setAttribute('aria-label', text || 'Выберите значение');
  }, [ariaLabel]);
  const close = () => { menu.current?.hidePopover(); setOpen(false); };
  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled || disabled) return;
    if (index !== selected) trackAction('filter_change');
    hapticSelection(); onChange(option.value); close(); trigger.current?.focus();
  };
  const reveal = () => {
    if (disabled || !options.length) return;
    const rect = trigger.current!.getBoundingClientRect();
    anchor.current = {top: rect.top, left: rect.left};
    const node = menu.current!;
    const below = window.innerHeight - rect.bottom - 8;
    const above = rect.top - 8;
    const down = below >= Math.min(240, above);
    const height = Math.max(44, Math.min(320, down ? below : above));
    Object.assign(node.style, {
      left: `${Math.max(8, Math.min(rect.left, window.innerWidth - rect.width - 8))}px`,
      top: `${down ? rect.bottom + 4 : Math.max(8, rect.top - height - 4)}px`,
      width: `${Math.min(rect.width, window.innerWidth - 16)}px`, maxHeight: `${height}px`,
    });
    setActive(selected >= 0 && !options[selected].disabled ? selected : Math.max(0, options.findIndex(option => !option.disabled)));
    node.showPopover(); setOpen(true);
  };
  useLayoutEffect(() => {
    if (!open) return;
    menu.current?.querySelector(`#${CSS.escape(`${listId}-${active}`)}`)?.scrollIntoView({block: 'nearest'});
    const dismiss = () => { menu.current?.hidePopover(); setOpen(false); };
    window.addEventListener('resize', dismiss);
    const scroll = (event: Event) => {
      if (menu.current?.contains(event.target as Node)) return;
      const rect = trigger.current?.getBoundingClientRect();
      if (!rect || Math.abs(rect.top - anchor.current.top) > 1 || Math.abs(rect.left - anchor.current.left) > 1) dismiss();
    };
    window.addEventListener('scroll', scroll, true);
    return () => { window.removeEventListener('resize', dismiss); window.removeEventListener('scroll', scroll, true); };
  }, [open, active, listId]);
  const move = (step: number) => {
    for (let offset = 1; offset <= options.length; offset++) {
      const index = (active + step * offset + options.length * 2) % options.length;
      if (!options[index].disabled) { setActive(index); break; }
    }
  };
  return <div ref={wrapper} className={`custom-select-wrapper ${open ? 'open' : ''} ${className}`}>
    <button ref={trigger} id={id} type="button" role="combobox" aria-label={label} aria-expanded={open}
      aria-controls={listId} aria-haspopup="listbox" aria-activedescendant={open ? `${listId}-${active}` : undefined}
      disabled={disabled} className="custom-select-trigger" onClick={() => open ? close() : reveal()}
      onKeyDown={event => {
        if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' ', 'Escape'].includes(event.key)) {
          event.preventDefault();
          if (event.key === 'Escape') { close(); return; }
          if (!open) { reveal(); return; }
          if (event.key === 'Enter' || event.key === ' ') choose(active);
          else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') move(event.key === 'ArrowDown' ? 1 : -1);
          else setActive(event.key === 'Home' ? Math.max(0, options.findIndex(option => !option.disabled)) : options.map(option => !option.disabled).lastIndexOf(true));
        } else if (event.key === 'Tab') close();
        else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          if (!open) reveal();
          const now = Date.now();
          search.current = {text: (now - search.current.time < 750 ? search.current.text : '') + event.key.toLowerCase(), time: now};
          const index = options.findIndex(option => !option.disabled && option.label.toLowerCase().startsWith(search.current.text));
          if (index >= 0) setActive(index);
        }
      }}><span>{options[selected]?.label || 'Выберите…'}</span><i className="select-arrow" aria-hidden="true" /></button>
    <div ref={menu} id={listId} role="listbox" aria-label={label} popover="auto" className="custom-select-listbox"
      onToggle={event => { setOpen(event.newState === 'open'); }}>
      {options.map((option, index) => <div key={String(option.value)} id={`${listId}-${index}`} role="option"
        aria-selected={index === selected} aria-disabled={option.disabled || undefined}
        className={`custom-select-option ${index === active ? 'focused' : ''}`}
        onPointerMove={() => { if (!option.disabled) setActive(index); }}
        onMouseDown={event => event.preventDefault()} onClick={event => { event.preventDefault(); choose(index); }}>{option.label}</div>)}
    </div>
  </div>;
}

function optionText(node: ReactNode): string {
  return Children.toArray(node).map(child => isValidElement<{children?: ReactNode}>(child) ? optionText(child.props.children) : String(child)).join('');
}

/** JSX option declarations are configuration only; no system select is mounted. */
export function SelectField({children, value, onChange, disabled, className, id, 'aria-label': ariaLabel}: {
  children: ReactNode; value: string | number; onChange: (value: string) => void;
  disabled?: boolean; className?: string; id?: string; 'aria-label'?: string;
}) {
  const options = Children.toArray(children).filter(isValidElement).map(child => {
    const props = (child as ReactElement<{value?: string | number; children?: ReactNode; disabled?: boolean}>).props;
    const label = optionText(props.children);
    return {value: props.value ?? label, label, disabled: props.disabled};
  });
  return <CustomSelect options={options} value={value} onChange={next => onChange(String(next))} disabled={disabled}
    className={className} ariaLabel={ariaLabel} id={id} />;
}
