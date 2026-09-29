import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../helpers/api';

type Check = {id:string; season:number; round:number; state:string; note?:string;
  additions:Record<string,string | number>; retirement_group?:string[]; tie_expansion?:string[]; missing:string[]; conflict:boolean;
  changes:{user_id:number;old_points:number;new_points:number;old_max:number;new_max:number;delta:number}[];
  applied_by?:number; applied_at?:number};
type CalculatedRound = {season:number;round:number;event_name:string;missing:string[]};
const endpoint='/api/admin/tools/prediction-recovery';
const names:Record<string,string>={fastest_lap_driver:'Лучший круг',first_retirement_driver:'Первый сход',safety_car:'Машина безопасности'};
const states:Record<string,string>={ready:'Готово к проверке',waiting:'Ожидаем данные',unchanged:'Нет изменений',conflict:'Источники расходятся',applied:'Применено',stale:'Проверка устарела'};

export function PredictionRecovery() {
  const [season,setSeason]=useState(new Date().getFullYear());
  const [round,setRound]=useState(1);
  const [checks,setChecks]=useState<Check[]>([]);
  const [selected,setSelected]=useState<Check|null>(null);
  const [confirmation,setConfirmation]=useState('');
  const [notifyConfirmation,setNotifyConfirmation]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [batchBusy,setBatchBusy]=useState(false);
  const [batchChecks,setBatchChecks]=useState<Check[]>([]);
  const [batchProgress,setBatchProgress]=useState('');
  const [batchErrors,setBatchErrors]=useState<string[]>([]);
  const [batchConfirmation,setBatchConfirmation]=useState('');
  const batchCancelled=useRef(false);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true; apiRequest<Check[]>(endpoint).then(data=>{if(active)setChecks(data);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[]);
  const run=async(apply=false)=>{
    setBusy(true);setError('');setNotice('');
    try {
      if(apply && selected){await apiRequest(`${endpoint}/${selected.id}/apply`,{confirmation},'POST');setSelected(null);setConfirmation('');}
      else {setSelected(null);setConfirmation('');setSelected(await apiRequest<Check>(`${endpoint}/preview`,{season,round},'POST',180000));}
      setChecks(await apiRequest<Check[]>(endpoint));
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  };
  const checkAll=async()=>{
    batchCancelled.current=false;setBatchBusy(true);setBatchChecks([]);setBatchErrors([]);setBatchConfirmation('');setBatchProgress('Получаю список рассчитанных этапов…');
    try{
      const data=await apiRequest<{rounds:CalculatedRound[]}>(`${endpoint}/rounds`,{season});
      if(!data.rounds.length){setBatchProgress('В этом сезоне ещё нет рассчитанных этапов.');return;}
      for(let index=0;index<data.rounds.length;index++){
        if(batchCancelled.current)break;
        const item=data.rounds[index];
        setBatchProgress(`Проверено ${index} из ${data.rounds.length} · сейчас этап ${item.round}: ${item.event_name}`);
        try{
          const check=await apiRequest<Check>(`${endpoint}/preview`,{season:item.season,round:item.round},'POST',180000);
          setBatchChecks(previous=>[...previous,check]);
        }catch(e){setBatchErrors(previous=>[...previous,`Этап ${item.round}: ${e instanceof Error?e.message:String(e)}`]);}
      }
      setBatchProgress(batchCancelled.current?'Проверка остановлена. Уже полученные предпросмотры сохранены.':`Проверка ${data.rounds.length} этапов завершена.`);
      setChecks(await apiRequest<Check[]>(endpoint));
    }catch(e){setBatchErrors(previous=>[...previous,e instanceof Error?e.message:String(e)]);setBatchProgress('Проверка прервана.');}
    finally{setBatchBusy(false);}
  };
  const applyAll=async()=>{
    const ready=batchChecks.filter(check=>check.state==='ready');
    if(batchConfirmation!=='ПЕРЕСЧИТАТЬ ВСЕ' || !ready.length)return;
    batchCancelled.current=false;setBatchBusy(true);setBatchErrors([]);
    try{
      for(let index=0;index<ready.length;index++){
        if(batchCancelled.current)break;
        const check=ready[index];setBatchProgress(`Применено ${index} из ${ready.length} · сейчас этап ${check.round}`);
        try{
          await apiRequest(`${endpoint}/${check.id}/apply`,{confirmation:'ПЕРЕСЧИТАТЬ'},'POST',180000);
          setBatchChecks(previous=>previous.map(item=>item.id===check.id?{...item,state:'applied'}:item));
        }catch(e){setBatchErrors(previous=>[...previous,`Этап ${check.round}: ${e instanceof Error?e.message:String(e)}`]);}
      }
      setBatchProgress(batchCancelled.current?'Применение остановлено. Уже применённые этапы сохранены.':'Применение готовых этапов завершено. Рассылки не запускались.');
      setSelected(null);setChecks(await apiRequest<Check[]>(endpoint));
    }catch(e){setBatchErrors(previous=>[...previous,e instanceof Error?e.message:String(e)]);}
    finally{setBatchConfirmation('');setBatchBusy(false);}
  };
  const notify=async()=>{
    if(!selected || notifyConfirmation!=='ОТПРАВИТЬ')return;
    setBusy(true);setError('');setNotice('');
    try{
      const result=await apiRequest<{queued:number}>(`${endpoint}/${selected.id}/notify`,{confirmation:notifyConfirmation},'POST');
      setNotice(`Обновлённые итоги поставлены в очередь для ${result.queued} получателей. Повторное нажатие не создаст дублей.`);
      setNotifyConfirmation('');
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  };
  return <section className="admin-chart-card admin-tools"><h2>Дозагрузка результатов прогнозов</h2>
    <p>Новые данные не меняют очки без подтверждения. Добавляются отсутствующие категории или уточняется подтверждённая первая группа схода; прежние начисления сохраняются. Сам пересчёт ничего не рассылает; после применения можно отдельно подтвердить обновлённые итоги.</p>
    <fieldset disabled={busy||batchBusy}><label>Сезон<input type="number" min="1950" max="2100" value={season} onChange={e=>{setSeason(Number(e.target.value));setBatchChecks([]);setBatchErrors([]);setBatchProgress('');setBatchConfirmation('');}}/></label>
      <label>Этап<input type="number" min="1" max="40" value={round} onChange={e=>setRound(Number(e.target.value))}/></label>
      <button onClick={()=>void run()}>Загрузить данные и показать изменения</button></fieldset>
    <section aria-label="Проверка всего сезона"><h3>Все рассчитанные этапы сезона</h3>
      <p>Проверка проходит по этапам по очереди, чтобы не превысить лимит OpenF1. Будущие и ещё не рассчитанные этапы не затрагиваются. Оставьте страницу открытой до завершения; проверка сама не меняет баллы.</p>
      <button disabled={busy||batchBusy} onClick={()=>void checkAll()}>Проверить все этапы сезона {season}</button>
      {batchBusy&&<button onClick={()=>{batchCancelled.current=true;}}>Остановить после текущего этапа</button>}
      {batchProgress&&<p role="status">{batchProgress}</p>}
      {batchErrors.map((message,index)=><p role="alert" key={index}>{message}</p>)}
      {!!batchChecks.length&&<div><p>Проверено: {batchChecks.length}. Готово к применению: {batchChecks.filter(check=>check.state==='ready').length}. Без изменений: {batchChecks.filter(check=>check.state==='unchanged').length}. Ожидают данные: {batchChecks.filter(check=>check.state==='waiting').length}. Конфликты: {batchChecks.filter(check=>check.state==='conflict').length}.</p>
        {batchChecks.map(check=><p key={check.id}><button disabled={batchBusy} onClick={()=>setSelected(check)}>{check.season} · этап {check.round} · {states[check.state]||check.state}</button> {check.state==='ready'&&`· изменятся баллы у ${check.changes.filter(row=>row.delta!==0||row.old_max!==row.new_max).length} участников`}{check.missing.length?` · ещё нет: ${check.missing.map(key=>names[key]).join(', ')}`:''}</p>)}
        {batchChecks.some(check=>check.state==='ready')&&<fieldset disabled={batchBusy||busy}><label>Чтобы применить все готовые пересчёты, введите ПЕРЕСЧИТАТЬ ВСЕ<input value={batchConfirmation} onChange={e=>setBatchConfirmation(e.target.value)}/></label><button disabled={batchConfirmation!=='ПЕРЕСЧИТАТЬ ВСЕ'} onClick={()=>void applyAll()}>Применить все готовые этапы</button><small>Каждый этап проверяется повторно перед записью. Конфликты и этапы без новых данных пропускаются. Рассылки не запускаются.</small></fieldset>}
      </div>}
    </section>
    {busy&&<p role="status">Операция выполняется…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {selected&&<article><h3>{selected.season} · этап {selected.round}: {states[selected.state]}</h3>
      {selected.note&&<p>{selected.note}</p>}{selected.conflict&&<p>Источник также противоречит уже сохранённым фактам. Эти факты не заменяются.</p>}
      <ul>{Object.entries(selected.additions).map(([key,value])=><li key={key}>{names[key]}: {key==='safety_car'?(value?'Да':'Нет'):value}</li>)}</ul>
      {!!selected.retirement_group?.length&&<p>Первая группа схода: {selected.retirement_group.join(', ')}. Выбор любого из них приносит 2 балла за пункт.</p>}
      {!!selected.tie_expansion?.length&&<p>Уточнённая первая группа схода: {selected.tie_expansion.join(', ')}. Выбор любого из них приносит 2 балла за пункт.</p>}
      {!!selected.missing.length&&<p>Ещё нет данных: {selected.missing.map(key=>names[key]).join(', ')}.</p>}
      <details open><summary>Изменения баллов ({selected.changes.length} участников)</summary>{selected.changes.map(row=><p key={row.user_id}>Участник #{row.user_id}: {row.old_points}/{row.old_max} → {row.new_points}/{row.new_max} (+{row.delta})</p>)}</details>
      {selected.state==='ready'&&<fieldset disabled={busy||batchBusy}><label>Для применения введите ПЕРЕСЧИТАТЬ<input value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label><button disabled={confirmation!=='ПЕРЕСЧИТАТЬ'} onClick={()=>void run(true)}>Применить изменения очков</button></fieldset>}
      {selected.state==='applied'&&selected.missing.length===0&&<fieldset disabled={busy||batchBusy}><label>Для отдельной рассылки обновлённых итогов введите ОТПРАВИТЬ<input value={notifyConfirmation} onChange={e=>setNotifyConfirmation(e.target.value)}/></label><button disabled={notifyConfirmation!=='ОТПРАВИТЬ'} onClick={()=>void notify()}>Разослать обновлённые итоги</button><small>Сообщение с кнопкой «Таблица прогнозов» уйдёт один раз; повторный запрос безопасен.</small></fieldset>}
    </article>}
    <h3>Последние проверки и применения</h3>{checks.map(check=><p key={check.id}><button disabled={busy} onClick={()=>{setSelected(check);setConfirmation('');setNotifyConfirmation('');setNotice('');}}>{check.season} · этап {check.round} · {states[check.state]}</button>{check.applied_at&&` · админ #${check.applied_by}, ${new Date(check.applied_at*1000).toLocaleString()}`}</p>)}
  </section>;
}
