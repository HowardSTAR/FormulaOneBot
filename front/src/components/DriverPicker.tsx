import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { apiAssetUrl } from "../helpers/api";
import "./driver-picker.css";

export type PickerDriver = { code: string; name: string; constructorName?: string; disabled?: boolean };

function Portrait({ driver, season }: { driver: PickerDriver; season: number }) {
  const [failed, setFailed] = useState(false);
  return <span className="driver-picker-avatar">{failed ? driver.code : <img
    src={apiAssetUrl("/api/pilot-portrait", { code: driver.code, name: driver.name, season })}
    alt="" loading="lazy" onError={() => setFailed(true)} />}</span>;
}

export function DriverPicker({ drivers, value, season, label, disabled, onChange }: {
  drivers: PickerDriver[]; value: string; season: number; label: string; disabled?: boolean; onChange: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState({ top: 0, left: 0, width: 360, maxHeight: 500 });
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const title = useId();
  const selected = drivers.find(driver => driver.code === value);
  const filtered = drivers.filter(driver => `${driver.name} ${driver.code} ${driver.constructorName || ""}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  useEffect(() => {
    if (!open) return;
    const triggerElement = trigger.current!;
    const update = () => {
      const rect = triggerElement.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, 340), window.innerWidth - 24);
      const below = window.innerHeight - rect.bottom - 20;
      const height = Math.min(520, Math.max(below, rect.top - 20), window.innerHeight - 32);
      setPosition({ width, left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
        top: below >= height ? rect.bottom + 6 : Math.max(12, rect.top - height - 6), maxHeight: height });
    };
    update();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Keep the mobile keyboard closed until the user taps search.
    if (window.matchMedia("(min-width: 701px)").matches) input.current?.focus();
    else panel.current?.focus();
    window.addEventListener("resize", update);
    return () => { document.body.style.overflow = previous; window.removeEventListener("resize", update); triggerElement.focus(); };
  }, [open]);
  const close = () => setOpen(false);
  return <div className="driver-picker">
    <button type="button" ref={trigger} className="driver-picker-trigger" aria-label={`${label}: ${selected?.name || value || "Выберите пилота"}`}
      aria-haspopup="dialog" aria-expanded={open} disabled={disabled} onClick={() => { setSearch(""); setOpen(true); }}>
      {selected && <Portrait key={`${season}:${selected.code}`} driver={selected} season={season} />}
      <span>{selected?.name || value || "Выберите пилота"}</span><span aria-hidden="true">⌄</span>
    </button>
    {open && createPortal(<div className="driver-picker-overlay" onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={title} tabIndex={-1} className="driver-picker-panel" style={position}
        onKeyDown={event => {
          if (event.key === "Escape") { event.preventDefault(); close(); }
          const controls = Array.from(panel.current!.querySelectorAll<HTMLElement>("button:not(:disabled), input"));
          const index = controls.indexOf(document.activeElement as HTMLElement);
          if (event.key === "Tab") {
            event.preventDefault(); controls[(index + (event.shiftKey ? -1 : 1) + controls.length) % controls.length]?.focus();
          }
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault(); controls[(index + (event.key === "ArrowDown" ? 1 : -1) + controls.length) % controls.length]?.focus();
          }
        }}>
        <div className="driver-picker-handle" />
        <header><div><h2 id={title}>Выберите пилота</h2><small>{label}</small></div><button type="button" aria-label="Закрыть выбор пилота" onClick={close}>×</button></header>
        <input ref={input} className="driver-picker-search" aria-label="Поиск пилота" placeholder="Имя, команда или код" value={search} onChange={event => setSearch(event.target.value)} />
        <div className="driver-picker-list">
          {!filtered.length && <p role="status">Пилоты не найдены</p>}
          {filtered.map(driver => <button type="button" key={driver.code} className={`driver-picker-option ${driver.code === value ? "is-selected" : ""}`}
            disabled={driver.disabled} aria-pressed={driver.code === value} onClick={() => { onChange(driver.code); close(); }}>
            <Portrait key={`${season}:${driver.code}`} driver={driver} season={season} />
            <span className="driver-picker-name"><strong>{driver.name}</strong><small>{driver.disabled ? "Уже выбран на другое место" : driver.constructorName}</small></span>
            <span className="driver-picker-code">{driver.code}</span><span aria-hidden="true">{driver.code === value ? "✓" : ""}</span>
          </button>)}
        </div>
      </div>
    </div>, document.body)}
  </div>;
}
