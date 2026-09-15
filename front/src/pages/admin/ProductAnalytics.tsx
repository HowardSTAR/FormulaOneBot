import { useEffect,useState } from 'react';
import { apiRequest } from '../../helpers/api';

type Data = {
  reach:{telegram_reminders:number;push_reminders:number;silent_telegram:number};
  audience:{anonymous_browsers:number;accounts:number}; first_event:number|null;
  funnel:{opened:number;started:number;saved:number};
  visits:{platform:string;path:string;visits:number;browsers:number;anonymous_browsers:number}[];
  retention:{season:number;round:number;next_round:number;participants:number;returned:number}[];
  errors:{path:string;platform:string;error_code:number;occurrences:number}[];
  delivery:{channel:string;status:string;recipients:number}[];
  quality:{version:string;session:string;sessions:number;pending:number;excluded:number;mae:number|null;winner_brier:number|null}[];
};
const platforms:Record<string,string>={telegram:'Telegram',pwa:'PWA',browser:'Браузер',unknown:'Не определено'};
const percent=(n:number,d:number)=>d?`${(100*n/d).toFixed(1)}%`:'—';
export function ProductAnalytics(){
  const [days,setDays]=useState(30);
  const [result,setResult]=useState<{days:number;data?:Data;error?:string}|null>(null);
  useEffect(()=>{let active=true;apiRequest<Data>('/api/admin/tools/product-analytics',{days}).then(data=>{if(active)setResult({days,data});}).catch(()=>{if(active)setResult({days,error:'Не удалось загрузить аналитику'});});return()=>{active=false;};},[days]);
  const data=result?.days===days?result.data:undefined;
  return <section className="admin-chart-card admin-tools"><header><h2>Что помогает пользователям</h2><select aria-label="Период аналитики действий" value={days} onChange={e=>setDays(Number(e.target.value))}><option value={7}>7 дней</option><option value={30}>30 дней</option><option value={90}>90 дней</option></select></header>
    {!data?<p role="status">{result?.days===days&&result.error?result.error:'Загрузка…'}</p>:<>
      <p>Анонимных браузеров: {data.audience.anonymous_browsers}. Авторизованных аккаунтов: {data.audience.accounts}. Это разные единицы: один человек может использовать несколько браузеров и войти позже. Их нельзя складывать как количество людей.</p>
      <h3>Прогнозы: от открытия до сохранения</h3>
      <p>Открыли: {data.funnel.opened} → начали менять: {data.funnel.started} → сохранили: {data.funnel.saved}. Конверсия в сохранение: {percent(data.funnel.saved,data.funnel.opened)}.</p>
      <small>Единица — аккаунт × этап. Только последовательные шаги; сохранение подтверждается базой, не кликом. Редактирование учитывается тоже. События появились {data.first_event?new Date(data.first_event*1000).toLocaleString():'ещё не поступили'}; старые открытия не восстанавливаются.</small>
      <h3>Возвращаемость в прогнозы</h3>{data.retention.length?data.retention.map(r=><p key={`${r.season}:${r.round}`}>{r.season}: этап {r.round} → {r.next_round}: {r.returned} из {r.participants} ({percent(r.returned,r.participants)}).</p>):<p>Недостаточно завершённых этапов.</p>}
      <small>Переход между соседними рассчитанными этапами сезона, только сохранённые прогнозы. Это не все возвращения на сайт.</small>
      <details><summary>Популярность разделов по платформам</summary>{data.visits.map(v=><p key={`${v.platform}:${v.path}`}>{platforms[v.platform]||v.platform} · {v.path}: {v.browsers} браузеров, {v.visits} посещений, анонимных браузеров {v.anonymous_browsers}.</p>)}<small>Повторы одного пути за 5 минут объединяются. Платформу сообщает клиент; исторические визиты остаются «не определено».</small></details>
      <details><summary>Ошибки запросов по разделам</summary>{data.errors.length?data.errors.map(e=><p key={`${e.path}:${e.platform}:${e.error_code}`}>{e.path} · {platforms[e.platform]} · {e.error_code||'сеть/таймаут'}: {e.occurrences}</p>):<p>Зарегистрированных ошибок за период нет.</p>}<small>Клиентские сообщения о 5xx и сетевых ошибках, объединённые за 5 минут. Это не полный серверный журнал и не ошибки валидации формы.</small></details>
      <details><summary>Фактические статусы уведомлений</summary>{data.delivery.map(d=><p key={`${d.channel}:${d.status}`}>{d.channel} · {d.status}: {d.recipients}</p>)}<small>Единица — сообщение × получатель; sent означает принятие сервисом, не прочтение. Настройки каналов и охват — в блоке выше.</small></details>
      <h3>Качество математических прогнозов</h3>{data.quality.length?data.quality.map(q=><p key={`${q.version}:${q.session}`}>{q.version} · {q.session==='race'?'Гонка':'Квалификация'}: сессий {q.sessions}, MAE {q.mae?.toFixed(2)??'—'}, Brier {q.winner_brier?.toFixed(4)??'—'}. Ожидают факта: {q.pending}; неполных исключено: {q.excluded}.</p>):<p>Пока нет подходящих сохранённых прогнозов за период.</p>}
      <p>Сейчас выбраны напоминания хотя бы одной сессии: Telegram — {data.reach.telegram_reminders} аккаунтов, Push — {data.reach.push_reminders} аккаунтов с подпиской и участием в уведомлениях сайта. Без звука в Telegram: {data.reach.silent_telegram}. Это настройки, не гарантия доставки.</p>
      <small>Последний прогноз перед каждой сессией для каждой версии модели, без выбора самого удачного результата. Среднее по полностью сопоставленным сессиям; MAE — ошибка позиции, Brier — ошибка вероятностей первого места, меньше лучше. Малая выборка не подтверждает точность модели.</small>
    </>}
  </section>;
}
