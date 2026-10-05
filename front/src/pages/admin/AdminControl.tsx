import { SelectField } from '../../components/CustomSelect';
import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { PredictionRecovery } from './PredictionRecovery';
import './admin-control.css';

const labels:Record<string,string>={pending:'В очереди',sending:'Отправляется',retry:'Ожидает повтора',sent:'Принято сервисом',unknown:'Доставка не подтверждена',failed:'Ошибка',blocked:'Получатель недоступен',expired:'Срок истёк',cancelled:'Отменено'};
const facts:Record<string,string>={fastest_lap_driver:'лучший круг',first_retirement_driver:'первый сход',safety_car:'машина безопасности'};
type Summary={as_of:number;counts:Record<string,number>;oldest_pending:number|null;recoveries:Record<string,number>;push_configured:boolean;incomplete:{season:number;round:number;event_name:string;missing:string[]}[]};
type Delivery={event_key:string;recipient:number;channel:string;status:string;attempts:number;next_attempt:number;updated:number;message_id:number|null;error:string|null;expires:number};
const date=(value:number)=>new Date(value*1000).toLocaleString();

export function AdminControl({mode, onNavigate, onBusy}:{mode:'delivery'|'recovery';onNavigate:(section:string)=>void;onBusy:(busy:boolean)=>void}){
  const [summary,setSummary]=useState<Summary|null>(null);
  const [rows,setRows]=useState<{items:Delivery[];has_more:boolean}|null>(null);
  const [channel,setChannel]=useState('all');const [status,setStatus]=useState('failed');
  const [offset,setOffset]=useState(0);const [refresh,setRefresh]=useState(0);
  const [error,setError]=useState('');
  const [loaded,setLoaded]=useState('');
  const key=`${channel}:${status}:${offset}:${refresh}`;
  useEffect(()=>{
    let active=true;
    Promise.all([apiRequest<Summary>('/api/admin/tools/control'),mode==='delivery'?apiRequest<{items:Delivery[];has_more:boolean}>('/api/admin/tools/control/deliveries',{channel,status,offset}):Promise.resolve({items:[],has_more:false})])
      .then(([info,items])=>{if(active){setSummary(info);setRows(items);setError('');setLoaded(key);}})
      .catch(e=>{if(active){setError(e instanceof Error?e.message:String(e));setLoaded(key);}});
    return()=>{active=false;};
  },[channel,status,offset,refresh,key,mode]);
  const busy=loaded!==key;
  const groups = Object.values((rows?.items || []).reduce<Record<string, Delivery[]>>((result, row) => {
    const groupKey = `${row.channel}:${row.event_key}:${row.status}`;
    (result[groupKey] ||= []).push(row);
    return result;
  }, {}));
  return <section className="admin-control admin-tools"><header><div>{mode==='recovery'?<span>Полнота результатов</span>:<h2>Состояние доставки</h2>}</div><button disabled={busy} onClick={()=>setRefresh(v=>v+1)}>{busy?'Обновляем…':'Обновить сводку'}</button></header>
    {error&&<p role="alert">{error}</p>}{busy&&<p role="status">Обновляю данные…</p>}
    {summary&&mode==='delivery'&&<><small>Обновлено: {date(summary.as_of)}</small>
      <div className="control-metrics">{[['failed','Нужна диагностика'],['retry','Временные сбои'],['blocked','Получатель недоступен'],['unknown','Проверить доставку'],['pending','В очереди']].map(([s,title])=><button key={s} aria-pressed={status===s} onClick={()=>{setStatus(s);setOffset(0);}}><strong>{summary.counts[s]||0}</strong><span>{title}</span></button>)}</div>
      <p className="ui-data-context">Сводка: все каналы; завершённые доставки за последние 7 дней, очередь — за всё время. Фильтры ниже меняют только журнал.</p>
      <p className="ui-data-context">Ошибка: проверьте причину в технических сведениях. Получатель недоступен: повтор не поможет, пока он не восстановит доступ к боту. Неподтверждённую доставку нельзя повторять без проверки Telegram.</p>
      <p>Push: {summary.push_configured?'ключи настроены':'не настроен — проверьте VAPID'}. {summary.oldest_pending?`Самое старое ожидающее задание: ${date(summary.oldest_pending)}.`:'Ожидающих заданий нет.'}</p>
      {summary.incomplete.length>0&&<button onClick={()=>onNavigate('recovery')}>Неполных этапов: {summary.incomplete.length} · проверить →</button>}
      <details><summary>Что означают статусы</summary><p>Завершённые статусы в сводке — за 7 дней; ожидающие — за всё время. Это не проверка работы процесса бота. «Принято» не означает «прочитано». Неопределённые доставки нельзя повторять вслепую. Здесь нет автоматических отправок или сброса статусов.</p></details>
    </>}
    {mode==='recovery'?<>{!busy&&!error&&summary&&<details><summary>Неполные этапы: {summary.incomplete.length}</summary>{summary.incomplete.length?summary.incomplete.map(r=><p key={`${r.season}:${r.round}`}>{r.season} · этап {r.round} · {r.event_name}: нет данных — {r.missing.map(k=>facts[k]).join(', ')}.</p>):<p>Неполных этапов в загруженном списке нет.</p>}<small>Последние 30 неполных этапов. После применения пересчёта обновите сводку.</small></details>}<PredictionRecovery onBusy={onBusy}/></>:<>
      <div className="control-filters"><label>Канал<SelectField value={channel} onChange={e=>{setChannel(e);setOffset(0);}}><option value="all">Все каналы</option><option value="telegram">Telegram</option><option value="webpush">Web Push</option></SelectField></label><label>Статус<SelectField value={status} onChange={e=>{setStatus(e);setOffset(0);}}><option value="attention">Требуют внимания</option><option value="all">Все</option>{Object.entries(labels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</SelectField></label></div>
      <small>Журнал за всё время · до 50 записей на странице</small>
      {!busy&&!error&&rows?.items.length===0&&<p>По выбранным фильтрам заданий нет.</p>}
      {!busy&&!error&&groups.map(group => <details className="control-job-group" key={`${group[0].channel}:${group[0].event_key}:${group[0].status}`} open={group.length === 1}><summary>{labels[group[0].status]} · {group[0].channel === 'webpush' ? 'Web Push' : 'Telegram'} · {group[0].event_key} · получателей на странице: {group.length}</summary>{group.map(row=><article className={`control-job control-${row.status}`} key={`${row.channel}:${row.event_key}:${row.recipient}`}><header><strong>{labels[row.status]||row.status}</strong><span>{row.channel==='webpush'?'Web Push':'Telegram'} · {date(row.updated)}</span></header><code>{row.event_key}</code><p>{row.channel==='webpush'?'ID подписки':'ID чата'}: {row.recipient} · попыток: {row.attempts}</p>
        {row.status==='unknown'&&<p>Сервис мог принять сообщение. Требуется ручная проверка; автоматического повтора нет.</p>}{row.status==='blocked'&&<p>Бот заблокирован либо push-подписка больше не действует.</p>}
        <details><summary>Технические сведения</summary><p>Код: {row.error||'—'} · ID сообщения: {row.message_id??'—'}</p><p>Срок: {date(row.expires)}{row.next_attempt>0?` · следующая попытка: ${date(row.next_attempt)}`:''}</p></details></article>)}</details>)}
      <footer><button disabled={busy||offset===0} onClick={()=>setOffset(v=>Math.max(0,v-50))}>Назад</button><span>Страница {offset/50+1}</span><button disabled={busy||!!error||!rows?.has_more} onClick={()=>setOffset(v=>v+50)}>Далее</button></footer>
    </>}
  </section>;
}
