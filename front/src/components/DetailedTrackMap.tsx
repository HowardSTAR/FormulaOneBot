import { useEffect, useRef, useState, type ReactNode } from 'react';
import { getDetailedCircuit, type DetailedCircuit } from '../assets/detailedCircuits';
import { resolveCircuitAsset } from '../assets/circuitAsset';
import './detailed-track-map.css';
import './circuit-sheet.css';

const colors = ['#ee369f', '#ffd633', '#50baff'];
function Diagram({ data, turns, zones, pit }: {data: DetailedCircuit; turns: boolean; zones: boolean; pit: boolean}) {
  return <svg className="detailed-circuit-svg" viewBox={data.viewBox} role="img" aria-label={`${data.name}: повороты, секторы и зоны, ${data.season}`}>
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      {data.sectors.map((d,i) => <path key={`base${i}`} d={d} stroke="#343740" strokeWidth="25" />)}
      {data.sectors.map((d,i) => <path key={i} d={d} stroke={colors[i]} strokeWidth="16"><title>{`Сектор ${i+1}`}</title></path>)}
      {pit && <path d={data.pitLane} stroke="#f2f2f5" strokeWidth="4"><title>Пит-лейн — схематично</title></path>}
      {zones && data.zones.map(z => <path key={z.name} d={z.path} stroke="#ff443b" strokeWidth="6"><title>{`${z.name}: ${z.description}`}</title></path>)}
    </g>
    {turns && data.corners.map(([n,x,y]) => <g key={n} transform={`translate(${x} ${y})`}>
      <rect x="-28" y="-25" width="56" height="48" rx="14" fill="#f5f5f7" />
      <text textAnchor="middle" dominantBaseline="middle" fill="#101116" fontSize="38" fontWeight="800">{n}</text>
    </g>)}
    <g transform={`translate(${data.finish.join(' ')}) rotate(${data.finishAngle})`}>
      <rect x="-14" y="-10" width="28" height="20" fill="white" />
      {[[-14,-10],[0,-10],[-7,0],[7,0]].map(([x,y]) => <rect key={`${x},${y}`} x={x} y={y} width="7" height="10" fill="#101116" />)}
      <title>Старт / финиш (схематично)</title>
    </g>
    <path d={data.direction} fill="none" stroke="white" strokeWidth="5"><title>Направление движения</title></path>
    {zones && <>
      <circle cx={data.detection[0]} cy={data.detection[1]} r="10" fill="#00e99b" stroke="#111" strokeWidth="3"><title>{`Детекция Overtake: ${data.detectionDescription}`}</title></circle>
      <circle cx={data.activation[0]} cy={data.activation[1]} r="11" fill="#111" stroke="#00e99b" strokeWidth="5"><title>{`Активация Overtake: ${data.activationDescription}`}</title></circle>
    </>}
  </svg>;
}

export function DetailedTrackMap({eventName, location, season, preview, triggerLabel, dialogTitle, children}: {eventName: string; location?: string; season: number; preview?: ReactNode; triggerLabel?: string; dialogTitle?: string; children?: ReactNode}) {
  const assetName = resolveCircuitAsset(eventName, location, season);
  const data = getDetailedCircuit(assetName, season);
  const dialog = useRef<HTMLDialogElement>(null);
  const [turns,setTurns] = useState(true);
  const [zones,setZones] = useState(true);
  const [pit,setPit] = useState(true);
  const [zoom,setZoom] = useState(1);
  const sheet = Boolean(triggerLabel);
  const [sheetOpen, setSheetOpen] = useState(false);
  const motion = useRef<Animation | null>(null);
  useEffect(() => {
    if (!sheetOpen) return;
    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = 'hidden';
    return () => { root.style.overflow = overflow; };
  }, [sheetOpen]);
  useEffect(() => () => { motion.current?.cancel(); }, []);
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const close = () => {
    const element = dialog.current;
    if (!element?.open) return;
    const style = getComputedStyle(element);
    const from = { transform: style.transform, opacity: style.opacity };
    motion.current?.cancel();
    if (!sheet || reducedMotion()) { element.close(); return; }
    const animation = element.animate([from, { transform: 'translateY(100%)', opacity: 0 }], { duration: 180, easing: 'cubic-bezier(.4,0,1,1)' });
    motion.current = animation;
    animation.onfinish = () => { element.close(); animation.cancel(); };
  };
  const dialogEvents = {
    onClose: () => { setSheetOpen(false); },
    onCancel: (event: React.SyntheticEvent<HTMLDialogElement>) => { if (sheet) { event.preventDefault(); close(); } },
  };
  const dialogClass = `circuit-dialog${sheet ? ' circuit-dialog--sheet' : ''}`;
  const dismiss = <button type="button" className={sheet ? 'circuit-sheet-close' : undefined} aria-label={sheet ? 'Закрыть статистику трассы' : undefined} onClick={close}>
    {sheet ? <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg> : 'Закрыть'}
  </button>;
  const pending = <p className="circuit-data-pending">Подробная разметка {season} пока не проверена. {assetName === "Sepang Grand Prix" ? "Показан архивный контур Sepang; актуальные повороты и зоны 2026 ещё не подтверждены." : "На схеме показан только контур трассы."}</p>;
  const open = () => {
    const element = dialog.current;
    if (!element || element.open) return;
    setZoom(1); motion.current?.cancel(); element.showModal();
    if (!sheet) return;
    element.querySelector<HTMLButtonElement>('.circuit-sheet-close')?.focus({ preventScroll: true });
    element.querySelector<HTMLElement>('.circuit-zoom-scroll')?.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    setSheetOpen(true);
    if (!reducedMotion()) motion.current = element.animate([
      { transform: 'translateY(100%)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1 },
    ], { duration: 320, easing: 'cubic-bezier(.16,1,.3,1)' });
  };
  if (!data) return preview ? <>
    <button type="button" className="circuit-map-launcher" onClick={open} aria-label={`${triggerLabel || 'Открыть карту'}: ${eventName}`}>
      {preview}<span className="circuit-map-launcher-label">{triggerLabel || <>⛶ {assetName === "Sepang Grand Prix" ? "Архивный контур Sepang" : `Контур · ${season}`} · раскрыть</>}</span>
    </button>
    <dialog ref={dialog} {...dialogEvents} className={dialogClass} aria-label={triggerLabel ? `${triggerLabel}: ${eventName}` : `Карта ${eventName}`} onClick={e=>{if(e.target===e.currentTarget)close();}}>
      <header><strong>{dialogTitle || (sheet ? eventName : `${eventName} · ${season}`)}{sheet && <small>{season}</small>}</strong>{dismiss}</header>
      <div className="circuit-zoom-scroll"><div className="circuit-fallback-map">{preview}</div>{pending}{children}</div>
    </dialog>
  </> : pending;
  const [, , mapWidth, mapHeight] = data.viewBox.split(' ').map(Number);
  const diagram = <Diagram data={data} turns={turns} zones={zones} pit={pit} />;
  const controls = <div className="circuit-layer-controls">
      <label><input type="checkbox" checked={turns} onChange={e=>setTurns(e.target.checked)} />Повороты</label>
      <label><input type="checkbox" checked={zones} onChange={e=>setZones(e.target.checked)} />Overtake / SM</label>
      <label><input type="checkbox" checked={pit} onChange={e=>setPit(e.target.checked)} />Пит-лейн</label>
    </div>;
  const description = <><div className="circuit-legend">
      {colors.map((color,i)=><span key={color}><i style={{background:color}} />S{i+1}</span>)}
      <span>🏁 Старт / финиш</span><span><i style={{background:'#fff'}} />Пит-лейн</span>
      <span><i style={{background:'#00e99b'}} />Детекция</span><span><i className="activation-dot" />Активация Overtake</span>
      <span><i style={{background:'#ff443b'}} />SM-зоны</span>
    </div>
    <details><summary>Что означают зоны</summary>
      <p>Overtake: детекция — {data.detectionDescription}; активация — {data.activationDescription}.</p>
      {data.zones.map(z=><p key={z.name}><strong>{z.name}</strong> — {z.description}</p>)}
      <p>{data.sectorDescription}</p>
    </details>
    <p className="circuit-source">Схематичное расположение: не для измерения дистанций. Показаны зоны нормального сцепления; альтернативные точки — в описании. <a href={data.source} target="_blank" rel="noreferrer">{data.revision}</a></p></>;
  const expanded = <dialog ref={dialog} {...dialogEvents} aria-label={triggerLabel ? `${triggerLabel}: ${data.name}` : `Карта ${data.name} — увеличенный просмотр`} className={dialogClass} onClick={e=>{if(e.target===e.currentTarget)close();}}>
      <header><strong>{dialogTitle || (sheet ? data.name : `${data.name} · ${season}`)}{sheet && <small>{season}</small>}</strong><div>
        <button type="button" aria-label="Уменьшить карту" disabled={zoom===1} onClick={()=>setZoom(v=>Math.max(1,v-.5))}>−</button>
        <button type="button" aria-label="Увеличить карту" disabled={zoom===3} onClick={()=>setZoom(v=>Math.min(3,v+.5))}>+</button>
        {dismiss}
      </div></header>
      <div className="circuit-zoom-scroll">{controls}<div style={{width:`min(${zoom*100}%, ${zoom*70*mapWidth/mapHeight}dvh)`,margin:'0 auto'}}>{diagram}</div>{description}{children}</div>
    </dialog>;
  if (preview) return <>
    <button type="button" className="circuit-map-launcher" onClick={open} aria-label={`${triggerLabel || 'Открыть карту'}: ${eventName}`}>
      {preview}<span className="circuit-map-launcher-label">{triggerLabel || <>⛶ Подробная схема · {season}</>}</span>
    </button>{expanded}
  </>;
  return <section className="detailed-circuit" aria-label="Подробная карта трассы">
    <header><div><small>КАРТА ТРАССЫ · {season}</small><h2>{data.name}</h2></div><button type="button" onClick={open}>⛶ Увеличить</button></header>
    {controls}<div className="circuit-diagram">{diagram}</div>{description}{expanded}
  </section>;
}
