import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../helpers/api';

type Check = {id:string; season:number; round:number; state:string; note?:string;
  additions:Record<string,string | number>; retirement_group?:string[]; tie_expansion?:string[]; missing:string[]; conflict:boolean;
  changes:{user_id:number;old_points:number;new_points:number;old_max:number;new_max:number;delta:number}[];
  source?:string; manual_evidence?:{urls:Record<string,string>;reason:string;confirmed_at:string}|null;
  prepared_by?:number; applied_by?:number; applied_at?:number};
type CalculatedRound = {season:number;round:number;event_name:string;missing:string[];
  current:Record<string,string|number|null>;first_retirement_drivers:string[]};
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
  const [rounds,setRounds]=useState<CalculatedRound[]>([]);
  const [manualFastest,setManualFastest]=useState('');
  const [manualFastestUrl,setManualFastestUrl]=useState('');
  const [manualRetirements,setManualRetirements]=useState('');
  const [manualRetirementsUrl,setManualRetirementsUrl]=useState('');
  const [manualSafety,setManualSafety]=useState('');
  const [manualSafetyUrl,setManualSafetyUrl]=useState('');
  const [manualReason,setManualReason]=useState('');
  const batchCancelled=useRef(false);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true; apiRequest<Check[]>(endpoint).then(data=>{if(active)setChecks(data);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[]);
  useEffect(()=>{let active=true;apiRequest<{rounds:CalculatedRound[]}>(`${endpoint}/rounds`,{season}).then(data=>{if(active)setRounds(data.rounds);}).catch(()=>{if(active)setRounds([]);});return()=>{active=false;};},[season]);
  useEffect(()=>()=>{batchCancelled.current=true;},[]);
  const currentRound=rounds.find(item=>item.round===round);
  const run=async(apply=false)=>{
    setBusy(true);setError('');setNotice('');
    try {
      if(apply && selected){await apiRequest(`${endpoint}/${selected.id}/apply`,{confirmation},'POST');setSelected(null);setConfirmation('');setNotice(`Этап ${selected.round}: изменения баллов применены. Рассылка не запускалась.`);await apiRequest<{rounds:CalculatedRound[]}>(`${endpoint}/rounds`,{season}).then(data=>setRounds(data.rounds)).catch(()=>{});}
      else {setSelected(null);setConfirmation('');setSelected(await apiRequest<Check>(`${endpoint}/preview`,{season,round},'POST',180000));}
      setChecks(await apiRequest<Check[]>(endpoint));
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  };
  const manualPreview=async()=>{
    setBusy(true);setError('');setNotice('');setSelected(null);setConfirmation('');
    try{
      const group=manualRetirements.split(/[,;\s]+/).map(code=>code.trim().toUpperCase()).filter(Boolean);
      const preview=await apiRequest<Check>(`${endpoint}/manual-preview`,{
        season,round,fastest_lap_driver:manualFastest.trim().toUpperCase()||null,
        fastest_lap_url:manualFastestUrl.trim()||null,
        first_retirement_drivers:group,first_retirement_url:manualRetirementsUrl.trim()||null,
        safety_car:manualSafety===''?null:manualSafety==='yes',safety_car_url:manualSafetyUrl.trim()||null,
        reason:manualReason.trim(),
      },'POST');
      setSelected(preview);setChecks(await apiRequest<Check[]>(endpoint));
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
          let check=await apiRequest<Check>(`${endpoint}/preview`,{season:item.season,round:item.round},'POST',180000);
          if(check.note?.includes('HTTP 429')){
            setBatchProgress(`OpenF1 ограничил запросы. Пауза 65 секунд, затем повтор этапа ${item.round}…`);
            for(let second=0;second<65&&!batchCancelled.current;second++)await new Promise(resolve=>window.setTimeout(resolve,1000));
            if(!batchCancelled.current)check=await apiRequest<Check>(`${endpoint}/preview`,{season:item.season,round:item.round},'POST',180000);
          }
          setBatchChecks(previous=>[...previous,check]);
          if(check.note?.includes('HTTP 429')){
            setBatchErrors(previous=>[...previous,`Этап ${item.round}: лимит OpenF1 не снят после паузы. Проверка остановлена; повторите позднее.`]);
            batchCancelled.current=true;
          }
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
      await apiRequest<{rounds:CalculatedRound[]}>(`${endpoint}/rounds`,{season}).then(data=>setRounds(data.rounds)).catch(()=>{});
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
    <details className="pr-manual"><summary>Подтвердить факты вручную по источникам</summary>
      <p>Если API недоступно, внесите только проверенные факты. Для каждого заполненного пункта нужна ссылка на источник. Пустой пункт останется без данных. Подтверждённые ранее значения нельзя заменить; изменение баллов произойдёт только после отдельного применения предпросмотра.</p>
      {currentRound?<p><strong>{currentRound.event_name}</strong> · уже сохранено: лучший круг — {currentRound.current.fastest_lap_driver??'нет данных'}, первый сход — {currentRound.first_retirement_drivers.length?currentRound.first_retirement_drivers.join(', '):'нет данных'}, машина безопасности — {currentRound.current.safety_car===null?'нет данных':currentRound.current.safety_car?'Да':'Нет'}.</p>:<p>Этап {round} не найден среди рассчитанных этапов сезона {season}. Проверьте номер этапа.</p>}
      <fieldset disabled={busy||batchBusy||!currentRound}>
        <div className="pr-manual-grid">
          <label>Лучший круг · код пилота<input value={manualFastest} maxLength={4} placeholder="RUS" onChange={e=>setManualFastest(e.target.value)}/></label>
          <label>Источник лучшего круга · HTTPS<input type="url" value={manualFastestUrl} placeholder="https://..." onChange={e=>setManualFastestUrl(e.target.value)}/></label>
          <label>Первый сход · коды через запятую<input value={manualRetirements} placeholder="STR или STR, ALO при одновременном сходе" onChange={e=>setManualRetirements(e.target.value)}/></label>
          <label>Источник порядка сходов · HTTPS<input type="url" value={manualRetirementsUrl} placeholder="https://..." onChange={e=>setManualRetirementsUrl(e.target.value)}/></label>
          <label>Машина безопасности<select value={manualSafety} onChange={e=>setManualSafety(e.target.value)}><option value="">Не подтверждено</option><option value="yes">Да — был Safety Car</option><option value="no">Нет — не было Safety Car</option></select></label>
          <label>Источник по машине безопасности · HTTPS<input type="url" value={manualSafetyUrl} placeholder="https://..." onChange={e=>setManualSafetyUrl(e.target.value)}/></label>
        </div>
        <label>Почему источник подтверждает эти факты<textarea rows={3} maxLength={500} value={manualReason} placeholder="Кратко укажите круг или время события, особенно для первого схода и SC/VSC." onChange={e=>setManualReason(e.target.value)}/></label>
        <button onClick={()=>void manualPreview()}>Показать ручной предпросмотр</button>
      </fieldset>
    </details>
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
      {selected.source&&<p>Источник: {selected.source}{selected.prepared_by?` · внёс администратор #${selected.prepared_by}`:''}.</p>}
      {selected.note&&<p>{selected.note}</p>}{selected.conflict&&<p>Источник также противоречит уже сохранённым фактам. Эти факты не заменяются.</p>}
      {selected.manual_evidence&&<div><p>Обоснование: {selected.manual_evidence.reason}</p><ul>{Object.entries(selected.manual_evidence.urls).map(([key,url])=><li key={key}>{names[key]}: <a href={url} target="_blank" rel="noopener noreferrer">Открыть источник ↗</a></li>)}</ul><small>Ручная запись сохраняет ссылку, автора и время подтверждения в истории проверки.</small></div>}
      {selected.note?.includes('HTTP 429')&&<p>Лимит OpenF1 исчерпан. Баллы не менялись; подождите не менее минуты и запустите проверку снова.</p>}
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
