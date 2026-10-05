import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { PredictionResultBroadcast } from './PredictionResultBroadcast';

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

export function PredictionRecovery({onBusy}:{onBusy?:(busy:boolean)=>void}) {
  const [mode,setMode]=useState<'single'|'season'|'manual'>('single');
  const [season,setSeason]=useState(new Date().getFullYear());
  const [round,setRound]=useState(1);
  const [checks,setChecks]=useState<Check[]>([]);
  const [selected,setSelected]=useState<Check|null>(null);
  const [confirmation,setConfirmation]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [batchBusy,setBatchBusy]=useState(false);
  const [broadcastBusy,setBroadcastBusy]=useState(false);
  const [batchChecks,setBatchChecks]=useState<Check[]>([]);
  const [batchProgress,setBatchProgress]=useState('');
  const [batchErrors,setBatchErrors]=useState<string[]>([]);
  const [batchConfirmation,setBatchConfirmation]=useState('');
  const [rounds,setRounds]=useState<CalculatedRound[]>([]);
  const [roundsLoaded,setRoundsLoaded]=useState<number|null>(null);
  const [manualFastest,setManualFastest]=useState('');
  const [manualFastestUrl,setManualFastestUrl]=useState('');
  const [manualRetirements,setManualRetirements]=useState('');
  const [manualRetirementsUrl,setManualRetirementsUrl]=useState('');
  const [manualSafety,setManualSafety]=useState('');
  const [manualSafetyUrl,setManualSafetyUrl]=useState('');
  const [manualReason,setManualReason]=useState('');
  const batchCancelled=useRef(false);
  const [error,setError]=useState('');
  const [drivers,setDrivers]=useState<{code:string;name:string;constructorName?:string}[]>([]);
  const [driversError,setDriversError]=useState('');
  useEffect(()=>{
    let active=true; setDrivers([]); setDriversError('');
    setManualFastest(''); setManualRetirements(''); setManualSafety('');
    setManualFastestUrl(''); setManualRetirementsUrl(''); setManualSafetyUrl(''); setManualReason('');
    apiRequest<{season:number;round:number;results?:{code:string;name:string;team?:string}[]}>('/api/race-results',{season,round}).then(data=>{
      if (!active) return;
      if (data.season !== season || data.round !== round || !data.results?.length) throw new Error('No matching race roster');
      setDrivers(data.results.filter(driver=>driver.code).map(driver=>({code:driver.code,name:driver.name,constructorName:driver.team})));
    }).catch(()=>{if(active)setDriversError('Состав выбранной гонки не загружен. Выберите сезон или этап повторно.');});
    return()=>{active=false;};
  },[season,round]);
  useEffect(()=>{let active=true; apiRequest<Check[]>(endpoint).then(data=>{if(active)setChecks(data);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[]);
  useEffect(()=>{let active=true;apiRequest<{rounds:CalculatedRound[]}>(`${endpoint}/rounds`,{season}).then(data=>{if(active){setRounds(data.rounds);setRoundsLoaded(season);setRound(previous=>data.rounds.some(item=>item.round===previous)?previous:Math.max(1,...data.rounds.map(item=>item.round)));}}).catch(()=>{if(active){setRounds([]);setRoundsLoaded(season);setError('Не удалось загрузить список этапов. Обновите страницу или выберите сезон снова.');}});return()=>{active=false;};},[season]);
  useEffect(()=>()=>{batchCancelled.current=true;},[]);
  useEffect(()=>{onBusy?.(busy||batchBusy||broadcastBusy);return()=>onBusy?.(false);},[busy,batchBusy,broadcastBusy,onBusy]);
  useEffect(()=>{
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();};
    if(busy||batchBusy||broadcastBusy)window.addEventListener('beforeunload',warn);
    return()=>window.removeEventListener('beforeunload',warn);
  },[busy,batchBusy,broadcastBusy]);
  const currentRound=rounds.find(item=>item.round===round);
  const resetTarget=()=>{setSelected(null);setConfirmation('');setNotice('');setError('');setManualFastest('');setManualFastestUrl('');setManualRetirements('');setManualRetirementsUrl('');setManualSafety('');setManualSafetyUrl('');setManualReason('');};
  const selectCheck=(check:Check)=>{setSelected(check);setSeason(check.season);setRound(check.round);setMode('single');setConfirmation('');setNotice('');};
  const run=async(apply=false)=>{
    setBusy(true);setError('');setNotice('');
    try {
      if(apply && selected){await apiRequest(`${endpoint}/${selected.id}/apply`,{confirmation},'POST');setSelected({...selected,state:'applied'});setConfirmation('');setNotice(`Этап ${selected.round}: изменения баллов применены. Рассылка не запускалась.`);await apiRequest<{rounds:CalculatedRound[]}>(`${endpoint}/rounds`,{season}).then(data=>setRounds(data.rounds)).catch(()=>{});}
      else {setSelected(null);setConfirmation('');setSelected(await apiRequest<Check>(`${endpoint}/preview`,{season,round},'POST',180000));}
      setChecks(await apiRequest<Check[]>(endpoint));
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  };
  const manualPreview=async()=>{
    const urls=[manualFastestUrl,manualRetirementsUrl,manualSafetyUrl].filter(value=>value.trim());
    if(urls.some(value=>{try{return new URL(value.trim()).protocol!=='https:';}catch{return true;}})){setError('Укажите полную HTTPS-ссылку на подтверждающий материал.');return;}
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
  return <section className="admin-chart-card admin-tools"><h2>Проверка и пересчёт</h2>
    <ol className="admin-flow" aria-label="Порядок работы"><li>1 · Выбрать этап</li><li>2 · Проверить изменения</li><li>3 · Подтвердить пересчёт</li></ol>
    <p>Проверка не меняет баллы. Пересчёт требует подтверждения и не запускает рассылку.</p>
    <nav className="recovery-mode" aria-label="Способ проверки">{([['single','Один этап'],['season','Весь сезон'],['manual','Внести факты вручную']] as const).map(([value,label])=><button type="button" disabled={busy||batchBusy||broadcastBusy} aria-pressed={mode===value} key={value} onClick={()=>{setMode(value);setNotice('');setError('');}}>{label}</button>)}</nav>
    <fieldset className="recovery-target" disabled={busy||batchBusy||broadcastBusy}><label>Сезон<select value={season} onChange={e=>{resetTarget();setSeason(Number(e.target.value));setBatchChecks([]);setBatchErrors([]);setBatchProgress('');setBatchConfirmation('');}}>{Array.from({length:new Date().getFullYear()-1949},(_,i)=>new Date().getFullYear()-i).map(year=><option key={year} value={year}>{year}</option>)}</select></label>
      {mode!=='season'&&<label>Рассчитанный этап<select value={currentRound?round:''} disabled={roundsLoaded!==season} onChange={e=>{resetTarget();setRound(Number(e.target.value));}}><option value="" disabled>{roundsLoaded!==season?'Загружаем этапы…':'Выберите этап'}</option>{rounds.map(item=><option key={item.round} value={item.round}>Этап {item.round} · {item.event_name}{item.missing.length?' · неполные данные':''}</option>)}</select></label>}
      {mode==='single'&&<button disabled={!currentRound||roundsLoaded!==season} onClick={()=>void run()}>Проверить данные — без изменения баллов</button>}</fieldset>
    {roundsLoaded===season&&!rounds.length&&<p role="status">В выбранном сезоне пока нет рассчитанных этапов.</p>}
    {mode!=='season'&&roundsLoaded===season&&currentRound&&<PredictionResultBroadcast key={`${season}:${round}:${selected?.state==='applied'?selected.id:''}`} season={season} round={round} disabled={busy||batchBusy} onBusy={setBroadcastBusy}/>}
    {mode==='manual'&&<section className="pr-manual"><h3>Подтвердить факты по источникам</h3>
      <p>Если API недоступно, внесите только проверенные факты. Для каждого заполненного пункта нужна ссылка на источник. Пустой пункт останется без данных. Подтверждённые ранее значения нельзя заменить; изменение баллов произойдёт только после отдельного применения предпросмотра.</p>
      {currentRound?<p><strong>{currentRound.event_name}</strong> · уже сохранено: лучший круг — {currentRound.current.fastest_lap_driver??'нет данных'}, первый сход — {currentRound.first_retirement_drivers.length?currentRound.first_retirement_drivers.join(', '):'нет данных'}, машина безопасности — {currentRound.current.safety_car==null?'нет данных':currentRound.current.safety_car?'Да':'Нет'}.</p>:<p>Этап {round} не найден среди рассчитанных этапов сезона {season}. Проверьте номер этапа.</p>}
      <fieldset disabled={busy||batchBusy||broadcastBusy||!currentRound}>
        <div className="pr-manual-grid">
          {driversError&&<p role="alert">{driversError}</p>}
          <label>Лучший круг<select disabled={!drivers.length} value={manualFastest} onChange={e=>setManualFastest(e.target.value)}><option value="">Не подтверждать</option>{drivers.map(driver=><option value={driver.code} key={driver.code}>{driver.name} ({driver.code}){driver.constructorName ? ` · ${driver.constructorName}` : ''}</option>)}</select></label>
          <label>Источник лучшего круга · HTTPS<input type="url" value={manualFastestUrl} placeholder="https://..." onChange={e=>setManualFastestUrl(e.target.value)}/></label>
          <fieldset><legend>Первая группа схода · можно выбрать несколько пилотов</legend><p>Отметьте всех, кто сошёл одновременно первым. Выбор любого из них засчитывается один раз.</p>{drivers.map(driver=>{
            const group=manualRetirements.split(',').filter(Boolean);
            return <label key={driver.code}><input type="checkbox" checked={group.includes(driver.code)} onChange={e=>setManualRetirements((e.target.checked?[...group,driver.code]:group.filter(code=>code!==driver.code)).join(','))}/>{driver.name} ({driver.code}){driver.constructorName ? ` · ${driver.constructorName}` : ''}</label>;
          })}</fieldset>
          <label>Источник порядка сходов · HTTPS<input type="url" value={manualRetirementsUrl} placeholder="https://..." onChange={e=>setManualRetirementsUrl(e.target.value)}/></label>
          <label>Машина безопасности<select value={manualSafety} onChange={e=>setManualSafety(e.target.value)}><option value="">Не подтверждено</option><option value="yes">Да — был Safety Car</option><option value="no">Нет — не было Safety Car</option></select></label>
          <label>Источник по машине безопасности · HTTPS<input type="url" value={manualSafetyUrl} placeholder="https://..." onChange={e=>setManualSafetyUrl(e.target.value)}/></label>
          <p className="ui-data-context">Нужна прямая HTTPS-ссылка на классификацию, протокол или материал с подтверждением выбранного факта. Ссылка на главную страницу недостаточна. Проверка формы не применяет баллы.</p>
        </div>
        <label>Почему источник подтверждает эти факты<textarea rows={3} maxLength={500} value={manualReason} placeholder="Кратко укажите круг или время события, особенно для первого схода и SC/VSC." onChange={e=>setManualReason(e.target.value)}/></label>
        <button onClick={()=>void manualPreview()}>Показать ручной предпросмотр</button>
      </fieldset>
    </section>}
    {mode==='season'&&<section aria-label="Проверка всего сезона"><h3>Все рассчитанные этапы сезона</h3>
      <p>Проверка проходит по этапам по очереди, чтобы не превысить лимит OpenF1. Будущие и ещё не рассчитанные этапы не затрагиваются. Оставьте страницу открытой до завершения; проверка сама не меняет баллы.</p>
      <button disabled={busy||batchBusy||roundsLoaded!==season||!rounds.length} onClick={()=>void checkAll()}>Проверить все этапы сезона {season}</button>
      {batchBusy&&<button onClick={()=>{batchCancelled.current=true;}}>Остановить после текущего этапа</button>}
      {batchProgress&&<p role="status">{batchProgress}</p>}
      {batchErrors.map((message,index)=><p role="alert" key={index}>{message}</p>)}
      {!!batchChecks.length&&<div><p>Проверено: {batchChecks.length}. Готово к применению: {batchChecks.filter(check=>check.state==='ready').length}. Без изменений: {batchChecks.filter(check=>check.state==='unchanged').length}. Ожидают данные: {batchChecks.filter(check=>check.state==='waiting').length}. Конфликты: {batchChecks.filter(check=>check.state==='conflict').length}.</p>
        {batchChecks.map(check=><p key={check.id}><button disabled={batchBusy||busy||broadcastBusy} onClick={()=>selectCheck(check)}>{check.season} · этап {check.round} · {states[check.state]||check.state}</button> {check.state==='ready'&&`· изменятся баллы у ${check.changes.filter(row=>row.delta!==0||row.old_max!==row.new_max).length} участников`}{check.missing.length?` · ещё нет: ${check.missing.map(key=>names[key]).join(', ')}`:''}</p>)}
        {batchChecks.some(check=>check.state==='ready')&&<fieldset disabled={batchBusy||busy}><label>Чтобы применить все готовые пересчёты, введите ПЕРЕСЧИТАТЬ ВСЕ<input value={batchConfirmation} onChange={e=>setBatchConfirmation(e.target.value)}/></label><button disabled={batchConfirmation!=='ПЕРЕСЧИТАТЬ ВСЕ'} onClick={()=>void applyAll()}>Применить все готовые этапы</button><small>Каждый этап проверяется повторно перед записью. Конфликты и этапы без новых данных пропускаются. Рассылки не запускаются.</small></fieldset>}
      </div>}
    </section>}
    {busy&&<p role="status" className="history-loading">Операция выполняется. Дождитесь результата; повторный запрос не нужен.</p>}{error&&<p role="alert" className="admin-notice error">{error}</p>}{notice&&<p role="status" className="admin-notice success">{notice}</p>}
    {selected&&<article className="recovery-result"><h3>{selected.season} · этап {selected.round}</h3><p className="recovery-status">{states[selected.state]}</p>
      {selected.source&&<p>Источник: {selected.source}{selected.prepared_by?` · внёс администратор #${selected.prepared_by}`:''}.</p>}
      {selected.note&&<p>{selected.note}</p>}{selected.conflict&&<p>Источник также противоречит уже сохранённым фактам. Эти факты не заменяются.</p>}
      {selected.manual_evidence&&<div><p>Обоснование: {selected.manual_evidence.reason}</p><ul>{Object.entries(selected.manual_evidence.urls).map(([key,url])=><li key={key}>{names[key]}: <a href={url} target="_blank" rel="noopener noreferrer">Открыть источник ↗</a></li>)}</ul><small>Ручная запись сохраняет ссылку, автора и время подтверждения в истории проверки.</small></div>}
      {selected.note?.includes('HTTP 429')&&<p>Лимит OpenF1 исчерпан. Баллы не менялись; подождите не менее минуты и запустите проверку снова.</p>}
      <ul>{Object.entries(selected.additions).map(([key,value])=><li key={key}>{names[key]}: {key==='safety_car'?(value?'Да':'Нет'):value}</li>)}</ul>
      {!!selected.retirement_group?.length&&<p>Первая группа схода: {selected.retirement_group.join(', ')}. Выбор любого из них приносит 2 балла за пункт.</p>}
      {!!selected.tie_expansion?.length&&<p>Уточнённая первая группа схода: {selected.tie_expansion.join(', ')}. Выбор любого из них приносит 2 балла за пункт.</p>}
      {!!selected.missing.length&&<p>Ещё нет данных: {selected.missing.map(key=>names[key]).join(', ')}.</p>}
      <details open={selected.state==='ready'}><summary>Изменения баллов ({selected.changes.length} участников)</summary><div className="admin-table-wrap"><table><thead><tr><th>Участник</th><th>Было</th><th>Станет</th><th>Разница</th></tr></thead><tbody>{selected.changes.map(row=><tr key={row.user_id}><td>#{row.user_id}</td><td>{row.old_points}/{row.old_max}</td><td>{row.new_points}/{row.new_max}</td><td>{row.delta>0?'+':''}{row.delta}</td></tr>)}</tbody></table></div>{!selected.changes.length&&<p>Участников для пересчёта нет.</p>}</details>
      {selected.state==='ready'&&<fieldset disabled={busy||batchBusy||broadcastBusy}><label>Для применения введите ПЕРЕСЧИТАТЬ<input value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label><button disabled={confirmation!=='ПЕРЕСЧИТАТЬ'} onClick={()=>void run(true)}>Применить изменения очков</button></fieldset>}
    </article>}
    <details><summary>История проверок и применений · {checks.length}</summary>{checks.map(check=><p key={check.id}><button disabled={busy||batchBusy||broadcastBusy} onClick={()=>selectCheck(check)}>{check.season} · этап {check.round} · {states[check.state]}</button>{check.applied_at&&` · админ #${check.applied_by}, ${new Date(check.applied_at*1000).toLocaleString()}`}</p>)}{!checks.length&&<p>Проверок пока нет.</p>}</details>
  </section>;
}
