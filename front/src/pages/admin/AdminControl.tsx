import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { PredictionRecovery } from './PredictionRecovery';
import './admin-control.css';

const labels:Record<string,string>={pending:'В очереди',sending:'Отправляется',retry:'Ожидает повтора',sent:'Принято сервисом',unknown:'Доставка не подтверждена',failed:'Ошибка',blocked:'Получатель недоступен',expired:'Срок истёк',cancelled:'Отменено'};
const facts:Record<string,string>={fastest_lap_driver:'лучший круг',first_retirement_driver:'первый сход',safety_car:'машина безопасности'};
type Summary={as_of:number;counts:Record<string,number>;oldest_pending:number|null;recoveries:Record<string,number>;push_configured:boolean;incomplete:{season:number;round:number;event_name:string;missing:string[]}[]};
type Delivery={event_key:string;recipient:number;channel:string;status:string;attempts:number;next_attempt:number;updated:number;message_id:number|null;error:string|null;expires:number};
const date=(value:number)=>new Date(value*1000).toLocaleString();

export function AdminControl(){
  const [summary,setSummary]=useState<Summary|null>(null);
  const [rows,setRows]=useState<{items:Delivery[];has_more:boolean}|null>(null);
  const [channel,setChannel]=useState('all');const [status,setStatus]=useState('attention');
  const [offset,setOffset]=useState(0);const [refresh,setRefresh]=useState(0);
  const [section,setSection]=useState('delivery');const [error,setError]=useState('');
  const [loaded,setLoaded]=useState('');
  const key=`${channel}:${status}:${offset}:${refresh}`;
  useEffect(()=>{
    let active=true;
    Promise.all([apiRequest<Summary>('/api/admin/tools/control'),apiRequest<{items:Delivery[];has_more:boolean}>('/api/admin/tools/control/deliveries',{channel,status,offset})])
      .then(([info,items])=>{if(active){setSummary(info);setRows(items);setError('');setLoaded(key);}})
      .catch(e=>{if(active){setError(e instanceof Error?e.message:String(e));setLoaded(key);}});
    return()=>{active=false;};
  },[channel,status,offset,refresh,key]);
  const busy=loaded!==key;
  return <section className="admin-control admin-tools"><header><div><h2>Центр контроля</h2><p>Доставка уведомлений и полнота результатов — без поиска по серверным логам.</p></div><button disabled={busy} onClick={()=>setRefresh(v=>v+1)}>Обновить</button></header>
    {error&&<p role="alert">{error}</p>}{busy&&<p role="status">Обновляю данные…</p>}
    {summary&&<><small>Снимок: {date(summary.as_of)}. Завершённые статусы — за 7 дней; ожидающие — за всё время. Это не проверка работоспособности процесса бота.</small>
      <div className="control-metrics">{[['unknown','Не подтверждено'],['failed','Ошибки'],['pending','В очереди'],['retry','Повторы']].map(([s,title])=><button key={s} onClick={()=>{setStatus(s);setOffset(0);setSection('delivery');}}><strong>{summary.counts[s]||0}</strong><span>{title}</span></button>)}</div>
      <p>Push: {summary.push_configured?'ключи настроены':'не настроен — проверьте VAPID'}. {summary.oldest_pending?`Самое старое ожидающее задание: ${date(summary.oldest_pending)}.`:'Ожидающих заданий нет.'}</p>
      <p>Проверок пересчёта за 7 дней: готово {summary.recoveries.ready||0}, ожидание данных {summary.recoveries.waiting||0}, применено {summary.recoveries.applied||0}.</p>
    </>}
    <nav aria-label="Контроль процессов"><button aria-pressed={section==='delivery'} onClick={()=>setSection('delivery')}>Доставка</button><button aria-pressed={section==='recovery'} onClick={()=>setSection('recovery')}>Результаты и пересчёты</button></nav>
    {section==='recovery'?<><h3>Неполные результаты</h3>{!busy&&!error&&summary&&(summary.incomplete.length?summary.incomplete.map(r=><p key={`${r.season}:${r.round}`}>{r.season} · этап {r.round} · {r.event_name}: нет данных — {r.missing.map(k=>facts[k]).join(', ')}.</p>):<p>В загруженном списке нет неполных этапов.</p>)}<small>Показаны последние 30 неполных этапов. Проверить любой рассчитанный этап можно ниже. После применения пересчёта обновите сводку.</small><PredictionRecovery/></>:<>
      <div className="control-filters"><label>Канал<select value={channel} onChange={e=>{setChannel(e.target.value);setOffset(0);}}><option value="all">Все каналы</option><option value="telegram">Telegram</option><option value="webpush">Web Push</option></select></label><label>Статус<select value={status} onChange={e=>{setStatus(e.target.value);setOffset(0);}}><option value="attention">Требуют внимания</option><option value="all">Все</option>{Object.entries(labels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label></div>
      <p>Журнал — за всё время, по 50 записей. «Принято» не означает «прочитано». Неопределённые доставки нельзя повторять вслепую. В этом экране отправок и массового сброса статусов нет.</p>
      {!busy&&!error&&rows?.items.length===0&&<p>По выбранным фильтрам заданий нет.</p>}
      {!busy&&!error&&rows?.items.map(row=><article className={`control-job control-${row.status}`} key={`${row.event_key}:${row.recipient}`}><header><strong>{labels[row.status]||row.status}</strong><span>{row.channel==='webpush'?'Web Push':'Telegram'} · {date(row.updated)}</span></header><code>{row.event_key}</code><p>{row.channel==='webpush'?'ID подписки':'ID чата'}: {row.recipient} · попыток: {row.attempts}</p>
        {row.status==='unknown'&&<p>Сервис мог принять сообщение. Требуется ручная проверка; автоматического повтора нет.</p>}{row.status==='blocked'&&<p>Бот заблокирован либо push-подписка больше не действует.</p>}
        <details><summary>Технические сведения</summary><p>Код: {row.error||'—'} · ID сообщения: {row.message_id??'—'}</p><p>Срок: {date(row.expires)}{row.next_attempt>0?` · следующая попытка: ${date(row.next_attempt)}`:''}</p></details></article>)}
      <footer><button disabled={busy||offset===0} onClick={()=>setOffset(v=>Math.max(0,v-50))}>Назад</button><span>Страница {offset/50+1}</span><button disabled={busy||!!error||!rows?.has_more} onClick={()=>setOffset(v=>v+50)}>Далее</button></footer>
    </>}
  </section>;
}
