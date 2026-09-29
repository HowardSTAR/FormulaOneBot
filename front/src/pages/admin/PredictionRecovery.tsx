import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';

type Check = {id:string; season:number; round:number; state:string; note?:string;
  additions:Record<string,string | number>; missing:string[]; conflict:boolean;
  changes:{user_id:number;old_points:number;new_points:number;old_max:number;new_max:number;delta:number}[];
  applied_by?:number; applied_at?:number};
const endpoint='/api/admin/tools/prediction-recovery';
const names:Record<string,string>={fastest_lap_driver:'Лучший круг',first_retirement_driver:'Первый сход',safety_car:'Машина безопасности'};
const states:Record<string,string>={ready:'Готово к проверке',waiting:'Ожидаем данные',conflict:'Источники расходятся',applied:'Применено',stale:'Проверка устарела'};

export function PredictionRecovery() {
  const [season,setSeason]=useState(new Date().getFullYear());
  const [round,setRound]=useState(1);
  const [checks,setChecks]=useState<Check[]>([]);
  const [selected,setSelected]=useState<Check|null>(null);
  const [confirmation,setConfirmation]=useState('');
  const [notifyConfirmation,setNotifyConfirmation]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true; apiRequest<Check[]>(endpoint).then(data=>{if(active)setChecks(data);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[]);
  const run=async(apply=false)=>{
    setBusy(true);setError('');setNotice('');
    try {
      if(apply && selected){await apiRequest(`${endpoint}/${selected.id}/apply`,{confirmation},'POST');setSelected(null);setConfirmation('');}
      else {setSelected(null);setConfirmation('');setSelected(await apiRequest<Check>(`${endpoint}/preview`,{season,round},'POST'));}
      setChecks(await apiRequest<Check[]>(endpoint));
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
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
    <p>Новые данные не меняют очки без подтверждения. Добавляются только отсутствующие категории; прежние начисления сохраняются. Сам пересчёт ничего не рассылает; после применения можно отдельно подтвердить обновлённые итоги.</p>
    <fieldset disabled={busy}><label>Сезон<input type="number" min="1950" max="2100" value={season} onChange={e=>setSeason(Number(e.target.value))}/></label>
      <label>Этап<input type="number" min="1" max="40" value={round} onChange={e=>setRound(Number(e.target.value))}/></label>
      <button onClick={()=>void run()}>Загрузить данные и показать изменения</button></fieldset>
    {busy&&<p role="status">Операция выполняется…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {selected&&<article><h3>{selected.season} · этап {selected.round}: {states[selected.state]}</h3>
      {selected.note&&<p>{selected.note}</p>}{selected.conflict&&<p>Источник также противоречит уже сохранённым фактам. Эти факты не заменяются.</p>}
      <ul>{Object.entries(selected.additions).map(([key,value])=><li key={key}>{names[key]}: {key==='safety_car'?(value?'Да':'Нет'):value}</li>)}</ul>
      {!!selected.missing.length&&<p>Ещё нет данных: {selected.missing.map(key=>names[key]).join(', ')}.</p>}
      <details open><summary>Изменения баллов ({selected.changes.length} участников)</summary>{selected.changes.map(row=><p key={row.user_id}>Участник #{row.user_id}: {row.old_points}/{row.old_max} → {row.new_points}/{row.new_max} (+{row.delta})</p>)}</details>
      {selected.state==='ready'&&<fieldset disabled={busy}><label>Для применения введите ПЕРЕСЧИТАТЬ<input value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label><button disabled={confirmation!=='ПЕРЕСЧИТАТЬ'} onClick={()=>void run(true)}>Применить изменения очков</button></fieldset>}
      {selected.state==='applied'&&selected.missing.length===0&&<fieldset disabled={busy}><label>Для отдельной рассылки обновлённых итогов введите ОТПРАВИТЬ<input value={notifyConfirmation} onChange={e=>setNotifyConfirmation(e.target.value)}/></label><button disabled={notifyConfirmation!=='ОТПРАВИТЬ'} onClick={()=>void notify()}>Разослать обновлённые итоги</button><small>Сообщение с кнопкой «Таблица прогнозов» уйдёт один раз; повторный запрос безопасен.</small></fieldset>}
    </article>}
    <h3>Последние проверки и применения</h3>{checks.map(check=><p key={check.id}><button disabled={busy} onClick={()=>{setSelected(check);setConfirmation('');setNotifyConfirmation('');setNotice('');}}>{check.season} · этап {check.round} · {states[check.state]}</button>{check.applied_at&&` · админ #${check.applied_by}, ${new Date(check.applied_at*1000).toLocaleString()}`}</p>)}
  </section>;
}
