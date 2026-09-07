import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import type { GlossaryItem } from "../constants/glossaryData";
import { splitGlossaryText } from "../helpers/glossaryMatcher";
import "./GlossaryText.css";

function Term({ text, item }: { text: string; item: GlossaryItem }) {
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const trigger = useRef<HTMLAnchorElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const id = useId();
  const cancel = () => clearTimeout(timer.current);
  const close = () => { cancel(); setPosition(null); };
  const open = () => {
    cancel();
    const rect = trigger.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(360, window.innerWidth - 24);
    setPosition({
      left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
      top: Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 280)),
    });
  };
  const leave = () => { cancel(); timer.current = setTimeout(() => setPosition(null), 180); };
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!position) return;
    const dismiss = () => setPosition(null);
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) dismiss();
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        trigger.current?.focus({ preventScroll: true });
        dismiss();
      }
    };
    const scroll = (event: Event) => { if (!panel.current?.contains(event.target as Node)) dismiss(); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keyboard);
    document.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keyboard);
      document.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [position]);
  const href = `/wiki?term=${encodeURIComponent(item.id)}`;
  return <>
    <a ref={trigger} className="glossary-term" href={href}
      aria-haspopup="dialog" aria-expanded={!!position} aria-controls={position ? id : undefined}
      onPointerEnter={event => { if (event.pointerType === "mouse") open(); }}
      onPointerLeave={leave} onFocus={open} onBlur={leave}
      onKeyDown={event => {
        if (event.key === "ArrowDown" && position) {
          event.preventDefault(); panel.current?.querySelector("button")?.focus();
        }
      }}
      onClick={event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault(); open();
      }}>{text}</a>
    {position && createPortal(<div ref={panel} id={id} role="dialog" aria-label={item.termRu}
      className="glossary-hint" style={position}
      onPointerEnter={cancel} onPointerLeave={leave} onFocus={cancel}
      onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) leave(); }}>
      <button type="button" className="glossary-hint-close" aria-label="Закрыть подсказку"
        onClick={() => { trigger.current?.focus({ preventScroll: true }); close(); }}>×</button>
      <strong>{item.termRu}</strong><small>{item.termEn}</small>
      <p>{item.definition}</p>
      <Link to={href} onClick={close}>Подробнее в Wiki →</Link>
    </div>, document.body)}
  </>;
}

/** Use in informational text, never inside links, buttons or form labels. */
export function GlossaryText({ children }: { children: string }) {
  return <>{splitGlossaryText(children).map((part, index) => part.item
    ? <Term key={index} text={part.text} item={part.item} /> : part.text)}</>;
}
