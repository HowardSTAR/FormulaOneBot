import { SelectField } from '../../components/CustomSelect';
import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { PredictionRecovery } from './PredictionRecovery';
import './admin-control.css';

const labels:Record<string,string>={pending:'В очереди',sending:'Отправляется',retry:'Ожидает повтора',sent:'Принято сервисом',unknown:'Доставка не подтверждена',failed:'Ошибка',blocked:'Получатель недоступен',expired:'Срок истёк',cancelled:'Отменено'};
const facts:Record<string,string>={fastest_lap_driver:'лучший круг',first_retirement_driver:'первый сход',safety_car:'машина безопасности'};
type Operations={worker_healthy:boolean;disk_free_bytes:number;forecasts:{pending:number;oldest:number|null};backups:{last_verified:number|null;pending_replication:number;last_replicated:number|null};jobs:{name:string;last_success:number|null;error:string|null;overdue:boolean}[]};
type Summary={operations:Operations;as_of:number;counts:Record<string,number>;oldest_pending:number|null;recoveries:Record<string,number>;push_configured:boolean;incomplete:{season:number;round:number;event_name:string;missing:string[]}[]};
type Delivery={event_key:string;recipient:number;channel:string;status:string;attempts:number;next_attempt:number;updated:number;message_id:number|null;error:string|null;expires:number};
const date = (value: number) => new Date(value * 1000).toLocaleString('ru-RU');
type RecoveryTarget = { season: number; round: number };
const nextSteps: Record<string, string> = {
  failed: 'Проверьте соединение с сервисом и журнал отправки.',
  retry: 'Дождитесь следующей попытки.',
  blocked: 'Проверьте доступ к боту или подписку на push.',
  unknown: 'Сверьте отправку с сервисом перед повтором.',
};
const metrics = [
  ['failed', 'Ошибки', 'За 7 дней'],
  ['unknown', 'Не подтверждено', 'За 7 дней'],
  ['blocked', 'Получатель недоступен', 'За 7 дней'],
  ['retry', 'Ждут повтора', 'Вся очередь'],
  ['pending', 'В очереди', 'Вся очередь'],
] as const;

export function AdminControl({ mode, target, locked, onNavigate, onBusy }: { mode: 'delivery' | 'recovery'; target?: RecoveryTarget; locked: boolean; onNavigate: (section: string, target?: RecoveryTarget) => void; onBusy: (busy: boolean) => void }){
  const deliveryHeading = useRef<HTMLHeadingElement>(null);
  const [summary,setSummary]=useState<Summary|null>(null);
  const [rows,setRows]=useState<{items:Delivery[];has_more:boolean}|null>(null);
  const [channel,setChannel]=useState('all');const [status,setStatus]=useState('attention');
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
  return <section className="admin-control admin-tools"><header><div>{mode==='recovery'?<span>Полнота результатов</span>:<small>{summary ? `Обновлено: ${date(summary.as_of)}` : 'Состояние доставки'}</small>}</div><button disabled={busy} onClick={()=>setRefresh(v=>v+1)}>{busy?'Обновляем…':'Обновить сводку'}</button></header>
    {error&&<p role="alert">{error}</p>}{busy&&<p role="status">Обновляю данные…</p>}
    {mode === 'recovery' ? <>
      {!busy && !error && summary && <details open={summary.incomplete.length > 0}>
        <summary>Неполные этапы: {summary.incomplete.length}</summary>
        {summary.incomplete.length ? <ul className="admin-task-list">{summary.incomplete.map(r => <li key={`${r.season}:${r.round}`}>
          <div><strong>{r.event_name} · {r.season}, этап {r.round}</strong><p>Нет данных: {r.missing.map(k => facts[k] || k).join(', ')}.</p></div>
          <button type="button" disabled={locked || (target?.season === r.season && target.round === r.round)}
            onClick={() => onNavigate('recovery', r)}>{target?.season === r.season && target.round === r.round ? 'Этап открыт' : 'Открыть проверку'}</button>
        </li>)}</ul> : <p>Неполных этапов в загруженном списке нет.</p>}
      </details>}
      <PredictionRecovery key={target ? `${target.season}:${target.round}` : 'current'} initialSeason={target?.season} initialRound={target?.round} onBusy={onBusy} />
    </> : <>
      <h3 ref={deliveryHeading} className="control-queue-heading" tabIndex={-1}>{status === 'attention' ? 'Требует внимания' : 'Журнал доставки'}</h3>
      <div className="control-filters"><label>Канал<SelectField value={channel} onChange={e=>{setChannel(e);setOffset(0);}}><option value="all">Все каналы</option><option value="telegram">Telegram</option><option value="webpush">Web Push</option></SelectField></label><label>Статус<SelectField value={status} onChange={e=>{setStatus(e);setOffset(0);}}><option value="attention">Требуют внимания</option><option value="all">Все</option>{Object.entries(labels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</SelectField></label></div>
      <small>Журнал за всё время · фильтры действуют на этот список</small>
      {!busy&&!error&&rows?.items.length===0&&<p>По выбранным фильтрам заданий нет.</p>}
      {!busy && !error && groups.map(group => {
        const first = group[0];
        const id = `${first.channel}:${first.event_key}:${first.status}`;
        const channelName = first.channel === 'webpush' ? 'Web Push' : 'Telegram';
        const cards = group.map(row => <article className={`control-job control-${row.status}`} key={row.recipient}>
          <header><strong>{labels[row.status] || row.status} · {channelName}</strong><span>Статус от {date(row.updated)}</span></header>
          {nextSteps[row.status] && <p>{row.error && <>Код сбоя: <code className="control-error-code">{row.error}</code>. </>}{nextSteps[row.status]} {row.status === 'retry' && row.next_attempt > 0 && <>Следующая попытка: {date(row.next_attempt)}.</>}</p>}
          <details><summary>Технические сведения</summary>
            <code>{row.event_key}</code>
            <p>{row.channel === 'webpush' ? 'ID подписки' : 'ID чата'}: {row.recipient} · попыток: {row.attempts} · ID сообщения: {row.message_id ?? '—'}</p>
            <p>Срок: {date(row.expires)}</p>
          </details>
        </article>);
        return group.length === 1
          ? <div key={id}>{cards}</div>
          : <details className="control-job-group" key={id}><summary>{labels[first.status]} · {channelName} · {group.length} получателей на странице</summary><code>{first.event_key}</code>{cards}</details>;
      })}
      <footer><button disabled={busy||offset===0} onClick={()=>setOffset(v=>Math.max(0,v-50))}>Назад</button><span>Страница {offset/50+1}</span><button disabled={busy||!!error||!rows?.has_more} onClick={()=>setOffset(v=>v+50)}>Далее</button></footer>
      {summary && <details className="control-job">
        <summary>Сводка по всем каналам</summary>
        <div className="control-metrics">{metrics.map(([value, label, period]) => <button type="button" key={value} aria-pressed={status === value} onClick={() => {
          setStatus(value);
          setOffset(0);
          deliveryHeading.current?.focus();
        }}><strong>{summary.counts[value] || 0}</strong><span>{label}</span><small>{period}</small></button>)}</div>
      </details>}
      {summary && <details className="control-job" open={!summary.operations.worker_healthy || summary.operations.jobs.some(job => job.error || job.overdue) || !summary.operations.backups.last_verified}>
        <summary>Состояние сервера и резервных копий</summary>
        <p>Фоновые задачи: {summary.operations.worker_healthy ? 'работают' : 'нет свежего сигнала'}. Расчётов в очереди: {summary.operations.forecasts.pending}.</p>
        <p>Свободно на диске: {(summary.operations.disk_free_bytes / 1024 ** 3).toFixed(1)} ГБ. Резервная копия проверена: {summary.operations.backups.last_verified ? date(summary.operations.backups.last_verified) : 'ещё не проверялась'}.</p>
        <p>Ожидают переноса на ПК: {summary.operations.backups.pending_replication}. Последний перенос: {summary.operations.backups.last_replicated ? date(summary.operations.backups.last_replicated) : 'ещё не подтверждён'}.</p>
        <p>Push: {summary.push_configured ? 'ключи настроены' : 'ключи не настроены'}. {summary.oldest_pending ? `Самое старое задание: ${date(summary.oldest_pending)}.` : 'Ожидающих заданий нет.'}</p>
        <details><summary>Выполнение задач</summary>{summary.operations.jobs.map(job => <p key={job.name}><code>{job.name}</code> {job.last_success ? date(job.last_success) : 'ожидает первого запуска'}{job.error ? ' · ошибка выполнения' : ''}{job.overdue ? ' · просрочено' : ''}</p>)}</details>
      </details>}
      {summary && summary.incomplete.length > 0 && <div><button type="button" onClick={() => onNavigate('recovery')}>Проверить неполные этапы ({summary.incomplete.length})</button></div>}
    </>}
  </section>;
}
