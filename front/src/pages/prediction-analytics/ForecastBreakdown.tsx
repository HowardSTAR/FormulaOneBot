import { useState, type CSSProperties } from 'react';
import { SelectField } from '../../components/CustomSelect';
import { nextDriverSort, sortDrivers, type DriverSort, type DriverSortKey } from './driver-sort';
import './forecast-breakdown.css';

type Driver = {code:string;name:string;team:string;win:number;podium:number;top10:number;expected:number;range:number[];dnf:number;reasons:string[]};
type Scenario = {label:string;probability:number;why:string;top5:string[]};
const percent = (value:number) => value.toLocaleString('ru-RU',{style:'percent',minimumFractionDigits:1,maximumFractionDigits:1});
const decimal = (value:number) => value.toLocaleString('ru-RU',{maximumFractionDigits:1});
const width = (value:number) => `${Math.min(100,Math.max(0,value*100))}%`;

export function AllDrivers({drivers,isRace,actual,settled}:{drivers:Driver[];isRace:boolean;actual:ReadonlyMap<string,number>;settled:boolean}) {
  const [sort,setSort] = useState<DriverSort>({key:'expected',direction:'asc'});
  const [search,setSearch] = useState('');
  const options: {key:DriverSortKey;label:string}[] = [
    {key:'expected',label:'Среднее место'},{key:'win',label:isRace?'Вероятность победы':'Вероятность поула'},
    {key:'podium',label:'Вероятность топ-3'},{key:'top10',label:'Вероятность топ-10'},
    ...(isRace ? [{key:'dnf' as const,label:'Риск схода'}]:[]),
    {key:'name',label:'Имя пилота'},{key:'team',label:'Команда'},...(settled?[{key:'actual' as const,label:'Фактическое место'}]:[]),
  ];
  const needle = search.trim().toLocaleLowerCase('ru-RU');
  const rows = sortDrivers(drivers,sort,actual).filter(d => `${d.name} ${d.code} ${d.team}`.toLocaleLowerCase('ru-RU').includes(needle));
  const sortHeader = (key:DriverSortKey,label:string) => <th scope="col" aria-sort={sort.key===key ? sort.direction==='asc'?'ascending':'descending':'none'}><button type="button" onClick={()=>setSort(s=>nextDriverSort(s,key))} aria-label={`${label}: сортировать по ${nextDriverSort(sort,key).direction==='asc'?'возрастанию':'убыванию'}`}>{label}<span aria-hidden="true">{sort.key===key?(sort.direction==='asc'?'↑':'↓'):'↕'}</span></button></th>;
  const cell = (label:string,value:number,main=false) => <td className={main?'pa-driver-chance':'pa-driver-metric'}><span className="pa-driver-cell-label" aria-hidden="true">{label}</span><strong>{percent(value)}</strong><span className="pa-driver-bar" aria-hidden="true"><i style={{width:width(value)}} /></span></td>;
  return <details className="pa-fold pa-drivers-fold"><summary>Все пилоты<span>{drivers.length}</span></summary>
    <div className="pa-driver-tools">
      <label className="pa-driver-search">Найти пилота или команду<input type="search" name="driver-search" autoComplete="off" spellCheck={false} placeholder="Имя, код или команда…" value={search} onChange={e=>setSearch(e.target.value)} /></label>
      <label>Сортировать<SelectField value={sort.key} onChange={value=>setSort(nextDriverSort({key:sort.key,direction:sort.direction},value as DriverSortKey))}>{options.map(option=><option key={option.key} value={option.key}>{option.label}</option>)}</SelectField></label>
      <button className="pa-driver-direction" type="button" onClick={()=>setSort(s=>({...s,direction:s.direction==='asc'?'desc':'asc'}))} aria-label={`Изменить направление: сейчас по ${sort.direction==='asc'?'возрастанию':'убыванию'}`}><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M8 4v16m-4-4 4 4 4-4M16 20V4m-4 4 4-4 4 4" /></svg>{sort.direction==='asc'?'По возрастанию':'По убыванию'}</button>
    </div>
    <div className="pa-driver-context"><p>Диапазон мест — центральные 80% симуляций.{!isRace && ' Топ-10 — место в первой десятке, а не вероятность выхода в Q3.'}</p><span role="status">Показано: {rows.length} из {drivers.length}</span></div>
    {!rows.length ? <p className="pa-driver-empty">{drivers.length ? 'Ничего не найдено. Попробуйте другое имя или команду.' : 'В этом расчёте нет данных о пилотах.'}</p> : <table className="pa-driver-table"><caption className="pa-sr-only">Вероятности и ожидаемые позиции пилотов</caption><thead><tr>
      {sortHeader('name','Пилот')}{sortHeader('win',isRace?'Победа':'Поул')}{sortHeader('podium','Топ-3')}{sortHeader('top10','Топ-10')}{sortHeader('expected','Место')}{isRace && sortHeader('dnf','Сход')}{settled && sortHeader('actual','Факт')}
    </tr></thead><tbody>{rows.map(d=><tr key={d.code}>
      <th scope="row" className="pa-driver-identity"><details><summary><span className="pa-driver-code">{d.code}</span><span><strong>{d.name}</strong><small>{d.team}</small></span><svg className="pa-driver-expand" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m9 5 7 7-7 7" /></svg></summary><div className="pa-driver-reasons"><span>Что учитывает модель</span>{d.reasons.length ? <ul>{d.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul> : <p>Для этого пилота пояснения недоступны.</p>}</div></details></th>
      {cell(isRace?'Победа':'Поул',d.win,true)}{cell('Топ-3',d.podium)}{cell('Топ-10',d.top10)}
      <td className="pa-driver-position"><span className="pa-driver-cell-label" aria-hidden="true">Среднее место</span><strong>{decimal(d.expected)}</strong><small>Диапазон P{d.range[0]}–P{d.range[1]}</small></td>
      {isRace && <td className="pa-driver-risk"><span className="pa-driver-cell-label" aria-hidden="true">Риск схода</span><strong>{percent(d.dnf)}</strong></td>}
      {settled && <td className="pa-driver-actual"><span className="pa-driver-cell-label" aria-hidden="true">Результат</span><strong>{actual.has(d.code)?`P${actual.get(d.code)}`:'Нет данных'}</strong></td>}
    </tr>)}</tbody></table>}
  </details>;
}

export function ForecastScenarios({scenarios,drivers,isRace}:{scenarios:Scenario[];drivers:Driver[];isRace:boolean}) {
  const tones = ['var(--design-accent)','var(--design-wet)','var(--design-scale-medium)'];
  const tone = (index:number) => ({'--scenario-color':tones[index%tones.length]} as CSSProperties);
  return <details className="pa-fold pa-scenarios-fold"><summary>Сценарии {isRace?'гонки':'квалификации'}<span>{scenarios.length}</span></summary>
    {!scenarios.length ? <p className="pa-muted">Для этого расчёта сценарии недоступны.</p> : <>
      <figure className="pa-scenario-overview"><div className="pa-scenario-distribution" aria-hidden="true">{scenarios.map((s,i)=><span key={s.label} style={{...tone(i),flexBasis:width(s.probability)}} />)}</div><figcaption>Доли сценариев относятся к группам победителя. Пятёрки ниже — примеры порядка, а не вероятность точного порядка.</figcaption></figure>
      <div className="pa-scenario-grid">{scenarios.map((s,i)=><article className="pa-scenario-card" style={tone(i)} key={s.label}>
        <header><h3><span className="pa-scenario-dot" aria-hidden="true" />{s.label}</h3><strong>{percent(s.probability)}</strong></header>
        <p className="pa-scenario-why">{s.why}</p>
        <h4>Пример первой пятёрки</h4><ol>{s.top5.map((name,position)=>{
          const driver=drivers.find(d=>d.code===name||d.name===name);
          return <li key={`${name}-${position}`}><span className="pa-scenario-place" aria-hidden="true">P{position+1}</span><div><strong>{driver?.name??name}</strong>{driver && <small>{driver.team}</small>}</div></li>;
        })}</ol>
      </article>)}</div>
    </>}
  </details>;
}
