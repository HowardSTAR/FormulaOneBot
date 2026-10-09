import { SelectField } from '../../components/CustomSelect';
import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { pageTitles } from '../../helpers/pageTitles';
import './product-analytics.css';
type Data = {
  funnel:{opened:number;started:number;saved:number}; interaction_first:number|null;
  screens:{path:string;views:number;browsers:number}[];
  actions:{path:string;action:string;destination:string;clicks:number;browsers:number}[];
  retention:{season:number;round:number;next_round:number;participants:number;returned:number}[];
  errors:{path:string;platform:string;error_code:number;occurrences:number}[];
  quality:{version:string;session:string;sessions:number;pending:number;mae:number|null}[];
  referrals?:{arrived:number;activated:number;returned:number};
  posthog?:{configured:boolean;pending:number;failed:number;last_sent:number|null};
  notification_buttons?:{
    first_tracked:number|null;
    summary:{interactions:number;unique_users:number;callbacks:number;arrivals:number};
    items:{campaign:string;caption:string;channel:string;button:string;label:string;sent_at:number;
      clicks:number;unique_users:number;metric:'callback'|'arrival'}[];
  };
};
type Insights = {accounts:{total:number;new_users:number}; visitors:{unique_browsers:number;returning_browsers:number};
  inbox:{total:number;read_count:number}; queue:{pending:number;exhausted:number};reach:{members:number;push_users:number}};
const actions:Record<string,string>={calendar_open:'Открыть календарь',session_open:'Открыть расписание',results_open:'Открыть результаты',compare_open:'Сравнить пилотов',history_open:'Открыть историю',wiki_open:'Открыть справочник',prediction_submit:'Отправить прогноз',game_start:'Начать игру',game_restart:'Повторить игру',settings_save:'Сохранить настройки',favorites_toggle:'Изменить избранное',vote_submit:'Проголосовать',review_open:'Разобрать прогноз',filter_change:'Изменить фильтр',tab_change:'Переключить вкладку',back:'Вернуться назад',expand:'Раскрыть подробности',button:'Другая кнопка',navigate:'Перейти в раздел'};
const name=(path:string)=>pageTitles[path]||(path==='/share'?'Карточка участника':path);
actions.game_hit='Нажатие в игре';
const percent=(n:number,d:number)=>d?`${Math.round(100*n/d)}%`:'—';
export function AnalyticsDashboard(){
  const [days,setDays]=useState(30),[tab,setTab]=useState('overview'),[attempt,setAttempt]=useState(0);
  const [state,setState]=useState<{days:number;data:Data;insights:Insights}|null>(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;Promise.all([apiRequest<Data>('/api/admin/tools/product-analytics',{days}),apiRequest<Insights>('/api/admin/tools/insights',{days})])
    .then(([data,insights])=>{if(active)setState({days,data,insights});}).catch(()=>{if(active)setError('Не удалось загрузить аналитику. Попробуйте ещё раз.');});return()=>{active=false;};},[days,attempt]);
  const current=state?.days===days?state:null,data=current?.data,insights=current?.insights;
  const exportCsv=()=>{
    if(!data||!insights)return;
    const rows=[['Раздел','Показатель','Значение'],['Сводка','Период, дней',days],['Сводка','Браузеры',insights.visitors.unique_browsers],['Сводка','Вернувшиеся браузеры',insights.visitors.returning_browsers],['Прогнозы','Открыли',data.funnel.opened],['Прогнозы','Сохранили',data.funnel.saved],...data.screens.map(s=>['Экраны',name(s.path),s.views]),...data.actions.map(a=>['Действия',`${name(a.path)}: ${actions[a.action]||a.action}`,a.clicks]),
      ...(data.notification_buttons?.items||[]).flatMap(item=>[
        ['Кнопки бота',`${item.caption} · ${new Date(item.sent_at*1000).toLocaleString('ru-RU')} · ${item.label} · ${item.channel} · ${item.metric==='callback'?'нажатия':'переходы'}`,item.clicks],
        ['Кнопки бота',`${item.caption} · ${new Date(item.sent_at*1000).toLocaleString('ru-RU')} · ${item.label} · ${item.channel} · уникальные`,item.unique_users],
      ])];
    const url=URL.createObjectURL(new Blob(['\uFEFF'+rows.map(r=>r.map(v=>`"${String(v).replaceAll('"','""')}"`).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`analytics-${days}d.csv`;a.click();URL.revokeObjectURL(url);
  };
  const empty=<div className="pa-empty">Пока нет событий за этот период. Новые посещения и действия появятся после обновления сайта.</div>;
  return <section className="product-analytics"><header className="pa-toolbar"><label>Период<SelectField value={days} onChange={e=>{setError('');setDays(Number(e));}}><option value={7}>Последние 7 дней</option><option value={30}>Последние 30 дней</option><option value={90}>Последние 90 дней</option></SelectField></label><button disabled={!current} onClick={exportCsv}>Скачать CSV</button></header>
    <nav className="pa-tabs">{[['overview','Сводка'],['screens','Экраны'],['actions','Кнопки и действия'],['broadcasts','Кнопки бота'],['return','Возвращения']].map(([id,label])=><button key={id} onClick={()=>setTab(id)} className={tab===id?'active':''}>{label}</button>)}</nav>
    {error?<div role="alert"><p>{error}</p><button onClick={()=>{setError('');setState(null);setAttempt(v=>v+1);}}>Повторить</button></div>:!data||!insights?<p role="status">Загружаем показатели…</p>:<>
      {tab==='overview'&&<><div className="pa-metrics">{[['Посетили сайт',insights.visitors.unique_browsers,'уникальных браузеров'],['Вернулись в другой день',percent(insights.visitors.returning_browsers,insights.visitors.unique_browsers),`${insights.visitors.returning_browsers} браузеров за период`],['Новых аккаунтов',insights.accounts.new_users||0,'зарегистрировано за период'],['Сохранили прогноз',data.funnel.saved,'участий в этапах за период']].map(([label,value,hint])=><article key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></article>)}</div>
        <section className="pa-card"><h3>Доходят ли до прогноза?</h3><div className="pa-funnel">{[['Открыли',data.funnel.opened],['Начали заполнять',data.funnel.started],['Сохранили',data.funnel.saved]].map(([label,n])=><article key={label}><span>{label}</span><strong>{n}</strong></article>)}</div><p>Сохранение после открытия: <strong>{percent(data.funnel.saved,data.funnel.opened)}</strong></p><details><summary>Как считаем</summary><p>Один аккаунт на одном этапе — одно участие. Сохранение подтверждается сервером. Повторное редактирование не создаёт нового участия. Старые открытия до начала сбора не восстановлены.</p></details></section>
        <section className="pa-card"><h3>Что открывают чаще всего</h3>{data.screens.length?<div className="pa-list">{data.screens.slice(0,5).map(s=><div key={s.path}><span>{name(s.path)}</span><strong>{s.views} открытий</strong></div>)}</div>:empty}</section></>}
      {tab==='screens'&&<section className="pa-card"><h3>Посещаемость экранов</h3><p>Открытия показывают частоту использования, браузеры — охват.</p>{data.screens.length?<div className="pa-table"><table><thead><tr><th>Экран</th><th>Открытия</th><th>Браузеры</th></tr></thead><tbody>{data.screens.map(s=><tr key={s.path}><th>{name(s.path)}</th><td data-label="Открытия">{s.views}</td><td data-label="Браузеры">{s.browsers}</td></tr>)}</tbody></table></div>:empty}</section>}
      {tab==='broadcasts'&&<section className="pa-card"><h3>Кнопки бота</h3>
        <p>Здесь учитываются кнопки меню, кнопки под сообщениями и рассылки. Новые кнопки добавляются автоматически при отправке. Для ссылок и Mini App F1Hub считаем открытие страницы, например «Мой прогноз». Telegram не сообщает о нажатиях на внешние ссылки.</p>
        <div className="pa-funnel">{[['Нажатия в боте',data.notification_buttons?.summary.callbacks||0],['Переходы на сайт',data.notification_buttons?.summary.arrivals||0],['Уникальные',data.notification_buttons?.summary.unique_users||0]].map(([label,n])=><article key={label}><span>{label}</span><strong>{n}</strong></article>)}</div>
        {data.notification_buttons?.items.length?<div className="pa-table"><table><thead><tr><th>Кнопка и источник</th><th>Канал</th><th>Нажатия / переходы</th><th>Уникальные</th></tr></thead><tbody>{data.notification_buttons.items.map(item=><tr key={`${item.campaign}:${item.channel}:${item.button}`}><th>{item.label}<small>{item.caption} · {new Date(item.sent_at*1000).toLocaleString('ru-RU')}</small></th><td data-label="Канал">{item.channel==='telegram'?'Telegram':'Веб / push'}</td><td data-label={item.metric==='callback'?'Нажатия':'Переходы'}>{item.clicks}</td><td data-label="Уникальные">{item.unique_users}</td></tr>)}</tbody></table></div>:<div className="pa-empty">Пока нет данных о кнопках за этот период. Откройте меню бота или отправьте сообщение с кнопками.</div>}
        <p>Уникальные в боте считаются по пользователю Telegram, на сайте — по аккаунту, а без входа — по браузеру. Ввод текста, совпадающего с кнопкой клавиатуры меню, тоже считается нажатием. Повторное нажатие считается новым событием; повторная обработка одного события — нет. Сбор начат: {data.notification_buttons?.first_tracked?new Date(data.notification_buttons.first_tracked*1000).toLocaleString('ru-RU'):'ожидаем кнопки'}. Прошлые нажатия и переходы не восстанавливаются. Показаны до 200 строк.</p>
      </section>}
      {tab==='actions'&&<section className="pa-card"><h3>На что нажимают чаще всего</h3><p>До 30 самых частых сочетаний действия и экрана. Нажатие показывает интерес; успешное сохранение считается отдельно.</p>{data.actions.length?<div className="pa-table"><table><thead><tr><th>Действие</th><th>Экран</th><th>Нажатия</th><th>Браузеры</th></tr></thead><tbody>{data.actions.map(a=><tr key={`${a.path}:${a.action}:${a.destination}`}><th>{actions[a.action]||a.action}{a.destination&&<small>→ {name(a.destination)}</small>}</th><td data-label="Экран">{name(a.path)}</td><td data-label="Нажатия">{a.clicks}</td><td data-label="Браузеры">{a.browsers}</td></tr>)}</tbody></table></div>:empty}</section>}
      {tab==='return'&&<><section className="pa-card"><h3>Возвращаются ли на следующий этап?</h3><p>Участники, сохранившие прогноз в двух соседних рассчитанных этапах.</p>{data.retention.length?<div className="pa-list">{data.retention.map(r=><div key={`${r.season}:${r.round}`}><span>{r.season} · этап {r.round} → {r.next_round}</span><strong>{r.returned} из {r.participants} · {percent(r.returned,r.participants)}</strong></div>)}</div>:<p>Нужны два рассчитанных этапа с участниками.</p>}</section><section className="pa-card"><h3>Приглашения друзей</h3><div className="pa-funnel">{[['Пришли',data.referrals?.arrived||0],['Начали участвовать',data.referrals?.activated||0],['Вернулись в прогнозы',data.referrals?.returned||0]].map(([label,n])=><article key={label}><span>{label}</span><strong>{n}</strong></article>)}</div></section></>}
      <details className="pa-card"><summary>PostHog и сбор данных</summary><p><strong>{data.posthog?.configured?'PostHog настроен':'PostHog ещё не настроен'}</strong></p>{data.posthog?.configured?<><p>В очереди: {data.posthog.pending}. С ошибкой отправки: {data.posthog.failed}.</p><p>Последняя отправка: {data.posthog.last_sent?new Date(data.posthog.last_sent*1000).toLocaleString('ru-RU'):'события ещё не отправлены'}.</p></>:<p>Встроенный сбор уже работает. Для PostHog нужны отдельный экземпляр и ключ проекта. Параметры POSTHOG_HOST и POSTHOG_PROJECT_KEY задаются на сервере.</p>}<p>Начало сбора кнопок и экранов: {data.interaction_first?new Date(data.interaction_first*1000).toLocaleString('ru-RU'):'ожидаем первое событие'}.</p><p>Содержимое форм, email, Telegram ID, параметры ссылок и записи экрана не собираются. Браузер — не обязательно отдельный человек.</p></details>
      <details className="pa-card"><summary>Ошибки и качество данных</summary><h3>Ошибки запросов</h3>{data.errors.length?data.errors.map(e=><p key={`${e.path}:${e.platform}:${e.error_code}`}>{name(e.path)}: {e.error_code||'сеть или таймаут'} — {e.occurrences}</p>):<p>Зарегистрированных ошибок за период нет.</p>}<h3>Математические прогнозы</h3>{data.quality.map(q=><p key={`${q.version}:${q.session}`}>{q.session==='race'?'Гонка':'Квалификация'}: проверено {q.sessions}, средняя ошибка позиции {q.mae?.toFixed(2)??'—'}, ожидают результатов {q.pending}.</p>)}<p>Малая выборка не подтверждает точность модели.</p></details>
      <details className="pa-card"><summary>Аккаунты и уведомления сейчас</summary><p>Аккаунтов: {insights.accounts.total}. Получателей сайта: {insights.reach.members}. С push: {insights.reach.push_users}.</p><p>За период: уведомлений {insights.inbox.total}, прочитано {insights.inbox.read_count||0}. В очереди сейчас: {insights.queue.pending||0}; требуют проверки: {insights.queue.exhausted||0}.</p></details>
    </>}
  </section>;
}
