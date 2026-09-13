// Local Vite-only QA entry; not included in the production application bundle.
import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { DetailedTrackMap } from './components/DetailedTrackMap';
import { getDetailedCircuit } from './assets/detailedCircuits';
import './circuit-preview.css';
const maps = import.meta.glob<string>('/public/static/circuit/*.svg', {query:'?raw',import:'default',eager:true});
const imageUrl = (event: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(maps[`/public/static/circuit/${event}.svg`])}`;
const events = Object.keys(maps)
  .map(path => path.split('/').pop()!.replace(/\.svg$/, ''))
  .sort((a,b) => a.localeCompare(b));
export function Preview() {
  const [mobile,setMobile] = useState(false);
  const [selected,setSelected] = useState<string|null>(null);
  return <main className="circuit-gallery" style={{maxWidth:mobile?390:1440}}>
    <header><div><small>TURBOTEARS / КАРТЫ ТРАСС</small><h1>Все трассы</h1>
      <p>{events.length} схем в проекте · {events.filter(event=>getDetailedCircuit(event,2026)).length} с подробной разметкой · сезон 2026</p></div>
      <button onClick={()=>setMobile(v=>!v)}>{mobile?'Десктоп':'Мобильная ширина'}</button></header>
    <p className="gallery-note">Готовые карты отмечены зелёным: повороты, секторы, пит-лейн и зоны сверены со схемой FIA указанной версии. Остальные — исходные контуры, ещё без проверенной разметки. Нажмите на карту, чтобы рассмотреть её крупнее.</p>
    {selected && <section className="gallery-selected" aria-label="Выбранная трасса">
      <button onClick={()=>setSelected(null)}>← Все трассы</button>
      <h2>{selected}</h2>
      <DetailedTrackMap key={selected} eventName={selected} season={2026} preview={
        <img className="gallery-large-contour" src={imageUrl(selected)} alt={`Контур ${selected}`} />
      } />
    </section>}
    <div className="circuit-gallery-grid">{events.map((event,index) => <button key={event} className="circuit-gallery-card" onClick={()=>{setSelected(event);window.scrollTo({top:0,behavior:'smooth'});}}>
      <span className="gallery-card-index">{String(index+1).padStart(2,'0')}</span>
      <img src={imageUrl(event)} alt={`Контур ${event}`} />
      <strong>{event}</strong>
      <span className={getDetailedCircuit(event,2026)?'gallery-status-ready':'gallery-status-pending'}>{getDetailedCircuit(event,2026)?'Повороты + секторы + зоны →':'Контур · разметка ещё не добавлена'}</span>
    </button>)}</div>
  </main>;
}
createRoot(document.getElementById('root')!).render(<Preview />);
