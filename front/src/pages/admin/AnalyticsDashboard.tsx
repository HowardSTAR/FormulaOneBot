import { SelectField } from '../../components/CustomSelect';
import { useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { pageTitles } from '../../helpers/pageTitles';
import './product-analytics.css';
type TrafficPeriod = { browsers: number; returning: number };
type Traffic = {
  start: number; end: number; previous_start: number; first_visit: number | null;
  current: TrafficPeriod; previous: TrafficPeriod | null;
};
type Data = {
  period?: { start: number; end: number };
  traffic?: Traffic;
  prediction_first?: number | null;
  first_saves?: number;
  funnel:{opened:number;started:number;saved:number}; interaction_first:number|null;
  screens:{path:string;views:number;browsers:number}[];
  actions:{path:string;action:string;destination:string;clicks:number;browsers:number}[];
  retention:{season:number;round:number;next_round:number;participants:number;returned:number}[];
  errors:{path:string;platform:string;error_code:number;occurrences:number}[];
  quality:{version:string;session:string;sessions:number;pending:number;excluded?:number;mae:number|null}[];
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
const numbers = new Intl.NumberFormat('ru-RU');
const percentages = new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 1 });
const timestamps = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short', timeZone: 'UTC' });
const date = (value?: number | null) => value ? timestamps.format(value * 1000) : 'Нет событий';
const percent = (n: number, d: number) => d > 0 ? percentages.format(n / d) : '—';
const tabs = [
  ['overview', 'Сводка'],
  ['usage', 'Сайт'],
  ['broadcasts', 'Кнопки бота'],
  ['return', 'Прогнозы'],
  ['quality', 'Качество данных'],
] as const;

function Metric({ label, value, note }: { label: string; value: ReactNode; note: ReactNode }) {
  return <div className="pa-metric"><dt>{label}</dt><dd>{value}</dd><dd className="pa-metric-note">{note}</dd></div>;
}

function Funnel({ funnel, first, start }: { funnel: Data['funnel']; first?: number | null; start?: number }) {
  const steps = [
    ['Открыли', funnel.opened],
    ['Начали заполнять', funnel.started],
    ['Впервые сохранили', funnel.saved],
  ] as const;
  return <section className="pa-card pa-funnel-card">
    <h3>Первое сохранение прогноза</h3>
    {funnel.opened ? <>
      <p className="pa-funnel-result"><strong>{percent(funnel.saved, funnel.opened)}</strong> от учтённых открытий дошли до первого сохранения</p>
      <ol className="pa-step-list">{steps.map(([label, count]) => <li key={label}>
        <span>{label}</span><strong>{numbers.format(count)}</strong>
        <span className="pa-step-track" aria-hidden="true"><span style={{ width: 100 * count / funnel.opened + '%' }} /></span>
      </li>)}</ol>
    </> : <p>За период нет учтённых открытий. Конверсию пока нельзя рассчитать.</p>}
    {start && first && first > start ? <p className="pa-coverage">Первое доступное открытие — {date(first)} UTC. В начале периода данных нет.</p> : null}
    <details><summary>Как считается воронка</summary>
      <p>Единица — аккаунт на одном этапе. Учитываем последовательность «открыли → начали → впервые сохранили» внутри периода. Сохранение подтверждает база, время сравниваем с точностью до секунды.</p>
      <p>Если открытие или начало не записалось, пара не попадёт в следующие шаги. Правки и пересчёты не считаются новым сохранением. Долю открытий нельзя переносить на всю аудиторию сайта.</p>
    </details>
  </section>;
}

function Summary({ data, insights }: { data: Data; insights: Insights }) {
  const current = data.traffic?.current ?? {
    browsers: insights.visitors.unique_browsers, returning: insights.visitors.returning_browsers ?? 0,
  };
  const previous = data.traffic?.previous;
  const change = previous?.browsers ? (current.browsers - previous.browsers) / previous.browsers : null;
  const trafficNote = change !== null
    ? `${change > 0 ? '+' : ''}${percentages.format(change)} к предыдущему периоду`
    : previous ? 'В предыдущем периоде нет базы для расчёта доли' : 'Сравнение пока недоступно';
  return <>
    <section className="pa-card pa-audience">
      <h3>Аудитория сайта</h3>
      <dl className="pa-overview-metrics">
        <Metric label="Побывали на сайте" value={numbers.format(current.browsers)} note={<>уникальных браузеров<br />{trafficNote}</>} />
        <Metric label="Вернулись в другой день" value={percent(current.returning, current.browsers)} note={`${numbers.format(current.returning)} из ${numbers.format(current.browsers)} браузеров`} />
        <Metric label="Новые регистрации" value={numbers.format(insights.accounts.new_users ?? 0)} note="аккаунтов за выбранный период" />
      </dl>
      <p>Браузеры и аккаунты — разные единицы. Возврат означает визиты в разные дни UTC.</p>
      <details><summary>Границы сравнения</summary>
        {data.traffic && <p>Визиты: {date(data.traffic.start)} — {date(data.traffic.end)} UTC. Предыдущий период: {date(data.traffic.previous_start)} — {date(data.traffic.start)} UTC.</p>}
        <p>Сравнение использует завершённые пятиминутные интервалы. Динамика появится, когда первое сохранённое посещение будет не позже начала предыдущего периода. Архивные аккаунты исключены из числа регистраций.</p>
      </details>
    </section>
    <Funnel funnel={data.funnel} first={data.prediction_first} start={data.period?.start} />
  </>;
}

const empty = <p className="pa-empty">За этот период событий нет.</p>;

function SiteUsage({ data }: { data: Data }) {
  return <>
    <section className="pa-card"><h3>Популярные экраны</h3>
      <p>Открытия показывают частоту, уникальные браузеры — охват отдельного экрана.</p>
      {data.screens.length ? <div className="pa-table"><table>
        <thead><tr><th scope="col">Экран</th><th scope="col">Открытия</th><th scope="col">Браузеры</th></tr></thead>
        <tbody>{data.screens.map(s => <tr key={s.path}><th scope="row">{name(s.path)}</th><td data-label="Открытия">{numbers.format(s.views)}</td><td data-label="Браузеры">{numbers.format(s.browsers)}</td></tr>)}</tbody>
      </table></div> : empty}
    </section>
    <details className="pa-card"><summary>Частые действия на сайте</summary>
      <p>До 30 сочетаний действия и экрана. Нажатие отражает попытку, результат операции учитывается отдельно.</p>
      {data.actions.length ? <div className="pa-table"><table>
        <thead><tr><th scope="col">Действие</th><th scope="col">Экран</th><th scope="col">Нажатия</th><th scope="col">Браузеры</th></tr></thead>
        <tbody>{data.actions.map(a => <tr key={`${a.path}:${a.action}:${a.destination}`}><th scope="row">{actions[a.action] || a.action}{a.destination && <small>→ {name(a.destination)}</small>}</th><td data-label="Экран">{name(a.path)}</td><td data-label="Нажатия">{numbers.format(a.clicks)}</td><td data-label="Браузеры">{numbers.format(a.browsers)}</td></tr>)}</tbody>
      </table></div> : empty}
    </details>
  </>;
}

function BotButtons({ data }: { data: Data }) {
  const report = data.notification_buttons;
  return <section className="pa-card"><h3>Как используют кнопки</h3>
    {report ? <>
      <dl className="pa-overview-metrics">
        <Metric label="Действия в боте" value={numbers.format(report.summary.callbacks)} note="Нажатия и команды меню" />
        <Metric label="Переходы на сайт" value={numbers.format(report.summary.arrivals)} note="Зафиксированные открытия" />
        <Metric label="Уникальные идентификаторы" value={numbers.format(report.summary.unique_users)} note="По двум каналам вместе" />
      </dl>
      {report.items.length ? <div className="pa-table"><table>
        <thead><tr><th scope="col">Кнопка и источник</th><th scope="col">Канал</th><th scope="col">Действия</th><th scope="col">Уникальные</th></tr></thead>
        <tbody>{report.items.map(item => <tr key={`${item.campaign}:${item.channel}:${item.button}`}><th scope="row">{item.label}<small>{item.caption} · {date(item.sent_at)} UTC</small></th><td data-label="Канал">{item.channel === 'telegram' ? 'Telegram' : 'Веб / push'}</td><td data-label={item.metric === 'callback' ? 'Нажатия' : 'Переходы'}>{numbers.format(item.clicks)}</td><td data-label="Уникальные">{numbers.format(item.unique_users)}</td></tr>)}</tbody>
      </table></div> : empty}
      <details><summary>Какие действия видны в отчёте</summary>
        <p>Telegram передаёт ответы на кнопки бота. Для ссылок внутри F1Hub фиксируем открытие страницы. Нажатия по внешним ссылкам Telegram не передаёт. Совпавшая команда меню засчитывается как действие.</p>
        <p>Идентификатор — аккаунт или браузер без входа. Один человек может учитываться несколько раз. Первый источник зарегистрирован: {date(report.first_tracked)}{report.first_tracked ? ' UTC' : ''}. В таблице до 200 строк.</p>
      </details>
    </> : <p>Источник данных о кнопках недоступен.</p>}
  </section>;
}

function Coverage({ data, insights }: { data: Data; insights: Insights }) {
  const sources = [
    ['Посещения сайта', data.traffic?.first_visit],
    ['Открытия экранов и действия', data.interaction_first],
    ['Открытия прогнозов', data.prediction_first],
  ] as const;
  return <>
    <section className="pa-card"><h3>Покрытие сбора</h3>
      <dl className="pa-list">{sources.map(([label, first]) => <div key={label}><dt>{label}</dt><dd>{date(first)}{first ? ' UTC' : ''}</dd></div>)}</dl>
      <p>Даты показывают первые сохранившиеся события. По ним видно, где период начинается раньше данных. Пропуски внутри периода по этим датам определить нельзя.</p>
      {data.first_saves !== undefined && <p>В базе {numbers.format(data.first_saves)} первых сохранений за период. Из них {numbers.format(data.funnel.saved)} связаны с последовательностью в воронке. Разница включает пропущенные события и сценарии сохранения вне учтённой последовательности.</p>}
      <p>{data.posthog?.configured
        ? `PostHog подключён. В очереди ${data.posthog.pending}, с ошибкой ${data.posthog.failed}. Последняя отправка: ${date(data.posthog.last_sent)}${data.posthog.last_sent ? ' UTC' : ''}.`
        : 'Отчёт использует встроенный сбор сайта. PostHog не подключён.'}</p>
    </section>
    <details className="pa-card"><summary>Ошибки запросов</summary>
      <p>Клиентские сообщения о 5xx и сетевых сбоях. Повторы за пять минут объединяются.</p>
      {data.errors.length ? data.errors.map(e => <p key={`${e.path}:${e.platform}:${e.error_code}`}>{name(e.path)} · {e.platform} · {e.error_code || 'сеть или таймаут'} · {numbers.format(e.occurrences)}</p>) : empty}
    </details>
    <details className="pa-card"><summary>Качество математических прогнозов</summary>
      {data.quality.length ? data.quality.map(q => <p key={`${q.version}:${q.session}`}>{q.version} · {q.session === 'race' ? 'Гонка' : 'Квалификация'} · проверено {q.sessions}, средняя ошибка позиции {q.mae?.toFixed(2) ?? '—'}, ожидают результатов {q.pending}{q.excluded ? `, исключено неполных ${q.excluded}` : ''}.</p>) : empty}
      <p>Среднюю ошибку сравнивайте с учётом числа проверенных сессий.</p>
    </details>
    <details className="pa-card"><summary>Аккаунты и уведомления</summary>
      <p>Сейчас: аккаунтов {insights.accounts.total}, получателей сайта {insights.reach.members}, с push {insights.reach.push_users ?? 0}. В очереди {insights.queue.pending ?? 0}, требуют проверки {insights.queue.exhausted ?? 0}.</p>
      <p>За выбранный период: создано уведомлений {insights.inbox.total}, отмечено прочитанными {insights.inbox.read_count ?? 0}.</p>
    </details>
  </>;
}

export function AnalyticsDashboard() {
  const [params, setParams] = useSearchParams();
  const days = [7, 90].includes(Number(params.get('days'))) ? Number(params.get('days')) : 30;
  const tab = tabs.find(([id]) => id === params.get('report'))?.[0] ?? 'overview';
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ days: number; attempt: number; data?: Data; insights?: Insights; error?: boolean }>();
  useEffect(() => {
    let active = true;
    Promise.all([
      apiRequest<Data>('/api/admin/tools/product-analytics', { days }),
      apiRequest<Insights>('/api/admin/tools/insights', { days }),
    ]).then(([data, insights]) => {
      if (active) setState({ days, attempt, data, insights });
    }).catch(() => {
      if (active) setState({ days, attempt, error: true });
    });
    return () => { active = false; };
  }, [days, attempt]);

  const current = state?.days === days && state.attempt === attempt ? state : null;
  const { data, insights } = current ?? {};
  const setFilter = (key: string, value: string) => setParams(previous => {
    const next = new URLSearchParams(previous);
    next.set(key, value);
    return next;
  });
  function exportCsv() {
    if (!data || !insights) return;
    const traffic = data.traffic;
    const rows = [
      ['Раздел', 'Показатель', 'Значение'],
      ['Период', 'Дней', days],
      ['Период', 'Начало (UTC)', data.period ? date(data.period.start) : ''],
      ['Период', 'Конец (UTC)', data.period ? date(data.period.end) : ''],
      ['Аудитория', 'Браузеры', traffic?.current.browsers ?? insights.visitors.unique_browsers],
      ['Аудитория', 'Вернувшиеся браузеры', traffic?.current.returning ?? insights.visitors.returning_browsers],
      ['Аудитория', 'Браузеры за предыдущий период', traffic?.previous?.browsers ?? 'Нет сравнения'],
      ['Аудитория', 'Новые аккаунты', insights.accounts.new_users ?? 0],
      ['Воронка · аккаунт × этап', 'Открыли', data.funnel.opened],
      ['Воронка · аккаунт × этап', 'Начали', data.funnel.started],
      ['Воронка · аккаунт × этап', 'Впервые сохранили', data.funnel.saved],
      ['Качество данных', 'Все первые сохранения в базе', data.first_saves ?? 'Нет данных'],
      ...data.screens.map(s => ['Экраны', name(s.path), s.views]),
      ...data.actions.map(a => ['Действия', `${name(a.path)}: ${actions[a.action] || a.action}`, a.clicks]),
      ...(data.notification_buttons?.items ?? []).flatMap(item => {
        const label = `${item.caption} · ${date(item.sent_at)} UTC · ${item.label} · ${item.channel}`;
        return [
          ['Кнопки бота', `${label} · ${item.metric === 'callback' ? 'нажатия' : 'переходы'}`, item.clicks],
          ['Кнопки бота', `${label} · уникальные`, item.unique_users],
        ];
      }),
    ];
    const cell = (value: string | number) => {
      const text = String(value);
      const safeText = typeof value === 'string' && (/^\s*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) ? `'${text}` : text;
      return `"${safeText.replaceAll('"', '""')}"`;
    };
    const csv = '\uFEFF' + rows.map(row => row.map(cell).join(';')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `analytics-${days}d.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return <section className="product-analytics">
    <header className="pa-toolbar">
      <label>Период<SelectField value={days} onChange={value => setFilter('days', value)}>
        <option value={7}>Последние 7 дней</option>
        <option value={30}>Последние 30 дней</option>
        <option value={90}>Последние 90 дней</option>
      </SelectField></label>
      <button type="button" disabled={!data || !insights} onClick={exportCsv}>Скачать CSV</button>
      {data?.period && <p>{date(data.period.start)} — {date(data.period.end)} UTC</p>}
    </header>
    <nav className="pa-tabs" aria-label="Разделы аналитики">{tabs.map(([id, label]) => <button type="button"
      key={id} aria-pressed={tab === id} onClick={() => setFilter('report', id)}>{label}</button>)}</nav>
    {current?.error ? <section className="pa-card">
      <p role="alert">Не удалось загрузить аналитику.</p><button type="button" onClick={() => setAttempt(v => v + 1)}>Повторить загрузку</button>
    </section> : !data || !insights ? <p role="status">Загружаем показатели…</p> : <>
      {tab === 'overview' && <Summary data={data} insights={insights} />}
      {tab === 'usage' && <SiteUsage data={data} />}
      {tab === 'broadcasts' && <BotButtons data={data} />}
      {tab === 'return' && <section className="pa-card"><h3>Возвращаются ли на следующий этап?</h3>
        <p>Доля участников этапа, сохранивших прогноз на следующем рассчитанном этапе того же сезона. Показаны до 30 последних пар этапов целиком, независимо от фильтра по дням.</p>
        {data.retention.length ? <dl className="pa-list">{data.retention.map(r => <div key={`${r.season}:${r.round}`}><dt>{r.season} · этап {r.round} → {r.next_round}</dt><dd>{r.returned} из {r.participants} · {percent(r.returned, r.participants)}</dd></div>)}</dl> : <p>Пока нет подходящих пар этапов.</p>}
        {data.referrals && <details><summary>Участники по приглашениям</summary><p>Приглашения, учтённые за выбранный период. Пришли: {data.referrals.arrived}. Активировались: {data.referrals.activated}. Вернулись в прогнозы: {data.referrals.returned}.</p></details>}
      </section>}
      {tab === 'quality' && <Coverage data={data} insights={insights} />}
    </>}
  </section>;
}
