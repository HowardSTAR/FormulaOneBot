import { useRef, useState, type ReactNode } from 'react';
import { getDetailedCircuit, type DetailedCircuit } from '../assets/detailedCircuits';
import './detailed-track-map.css';

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

export function DetailedTrackMap({eventName, season, preview}: {eventName: string; season: number; preview?: ReactNode}) {
  const data = getDetailedCircuit(eventName, season);
  const dialog = useRef<HTMLDialogElement>(null);
  const [turns,setTurns] = useState(true);
  const [zones,setZones] = useState(true);
  const [pit,setPit] = useState(true);
  const [zoom,setZoom] = useState(1);
  const pending = <p className="circuit-data-pending">Подробная разметка {season}: пока не проверена. На схеме показан только контур трассы.</p>;
  const open = () => {setZoom(1);dialog.current?.showModal();};
  if (!data) return preview ? <>
    <button type="button" className="circuit-map-launcher" onClick={open} aria-label={`Открыть карту: ${eventName}`}>
      {preview}<span className="circuit-map-launcher-label">⛶ Контур · {season} · раскрыть</span>
    </button>
    <dialog ref={dialog} className="circuit-dialog" aria-label={`Карта ${eventName}`} onClick={e=>{if(e.target===e.currentTarget)dialog.current?.close();}}>
      <header><strong>{eventName} · {season}</strong><button type="button" onClick={()=>dialog.current?.close()}>Закрыть</button></header>
      <div className="circuit-zoom-scroll"><div className="circuit-fallback-map">{preview}</div>{pending}</div>
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
  const expanded = <dialog ref={dialog} aria-label={`Карта ${data.name} — увеличенный просмотр`} className="circuit-dialog" onClick={e=>{if(e.target===e.currentTarget)dialog.current?.close();}}>
      <header><strong>{data.name} · {season}</strong><div>
        <button type="button" aria-label="Уменьшить карту" disabled={zoom===1} onClick={()=>setZoom(v=>Math.max(1,v-.5))}>−</button>
        <button type="button" aria-label="Увеличить карту" disabled={zoom===3} onClick={()=>setZoom(v=>Math.min(3,v+.5))}>+</button>
        <button type="button" onClick={()=>dialog.current?.close()}>Закрыть</button>
      </div></header>
      <div className="circuit-zoom-scroll">{controls}<div style={{width:`min(${zoom*100}%, ${zoom*70*mapWidth/mapHeight}dvh)`,margin:'0 auto'}}>{diagram}</div>{description}</div>
    </dialog>;
  if (preview) return <>
    <button type="button" className="circuit-map-launcher" onClick={open} aria-label={`Открыть карту: ${eventName}`}>
      {preview}<span className="circuit-map-launcher-label">⛶ Подробная схема · {season}</span>
    </button>{expanded}
  </>;
  return <section className="detailed-circuit" aria-label="Подробная карта трассы">
    <header><div><small>КАРТА ТРАССЫ · {season}</small><h2>{data.name}</h2></div><button type="button" onClick={open}>⛶ Увеличить</button></header>
    {controls}<div className="circuit-diagram">{diagram}</div>{description}{expanded}
  </section>;
}
