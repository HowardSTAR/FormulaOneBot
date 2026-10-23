// Design exploration only: fixed fictional data, no API requests or account mutations.
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { HomeIcon, type HomeIconName } from '../src/pages/index/HomeIcon';
import { ThemeToggle } from '../src/components/ThemeToggle';
import { getTheme, initializeTheme, setTheme, subscribeTheme } from '../src/helpers/theme';
import circuit from '../public/static/circuit/United States Grand Prix.svg?raw';
import '../src/assets/design-system.css';
import './home-glass-options.css';

const variants = {
  focus: { name: 'Фокус на этапе', lead: 'Ближайшая сессия — первое, что вы видите.', description: 'Компактная карточка этапа, расписание рядом и отдельная стеклянная навигация. Самый спокойный вариант для ежедневного использования.' },
  panorama: { name: 'Панорама трассы', lead: 'Гоночный характер, больше пространства.', description: 'Крупная схема трассы задаёт композицию. На десктопе — верхняя навигация, на телефоне — компактный акцент на этапе и плавающая панель снизу.' },
  pitwall: { name: 'Пит-уолл', lead: 'Расписание и чемпионат одним взглядом.', description: 'Меньше декоративного пространства, больше полезных данных. На широком экране расписание соседствует с зачётом; на телефоне остаётся простая вертикальная лента.' },
} as const;
type Variant = keyof typeof variants;
const query = new URLSearchParams(location.search);
const initialVariant: Variant = query.get('variant') === 'panorama' ? 'panorama' : query.get('variant') === 'pitwall' ? 'pitwall' : 'focus';
const isScreen = query.get('view') === 'screen';
const weekend = '/tests/home-design-preview.html?page=weekend&auth=member';
const trackMarkup = circuit.replaceAll('#15151E', 'currentColor');
const primary: { label: string; icon: HomeIconName; href: string }[] = [
  { label: 'Обзор', icon: 'home', href: '#overview' },
  { label: 'Уик-энд', icon: 'weekend', href: weekend },
  { label: 'Календарь', icon: 'calendar', href: '/season' },
  { label: 'Прогнозы', icon: 'predictions', href: '/predictions' },
];
const schedule = [
  { name: 'Практика 1', day: 'Сегодня', time: '20:30', iso: '2026-10-23T17:30:00Z', icon: 'practice' },
  { name: 'Спринт-квалификация', day: 'Сб, 24 окт.', time: '00:30', iso: '2026-10-23T21:30:00Z', icon: 'sprintQuali' },
  { name: 'Спринт', day: 'Сб, 24 окт.', time: '20:00', iso: '2026-10-24T17:00:00Z', icon: 'sprint' },
  { name: 'Квалификация', day: 'Вс, 25 окт.', time: '00:00', iso: '2026-10-24T21:00:00Z', icon: 'quali' },
  { name: 'Гонка', day: 'Вс, 25 окт.', time: '23:00', iso: '2026-10-25T20:00:00Z', icon: 'race' },
] satisfies { name: string; day: string; time: string; iso: string; icon: HomeIconName }[];
const drivers = [
  { name: 'Ландо Норрис', team: 'McLaren', points: 287 },
  { name: 'Оскар Пиастри', team: 'McLaren', points: 272 },
  { name: 'Макс Ферстаппен', team: 'Red Bull Racing', points: 255 },
  { name: 'Джордж Расселл', team: 'Mercedes', points: 214 },
];
const teams = [
  { name: 'McLaren', team: 'Уокинг', points: 559 },
  { name: 'Mercedes', team: 'Брэкли', points: 382 },
  { name: 'Ferrari', team: 'Маранелло', points: 361 },
  { name: 'Red Bull Racing', team: 'Милтон-Кинс', points: 329 },
];

function Brand() {
  return <a className="concept-brand" href="#overview" aria-label="TurboTears — обзор"><span>Turbo</span>Tears<span className="brand-dot" aria-hidden="true" /></a>;
}

function NavLinks({ mobile = false }: { mobile?: boolean }) {
  return <nav aria-label={mobile ? 'Основная навигация' : 'Разделы'}>{primary.map((item, i) => <a href={item.href} key={item.label} aria-current={i === 0 ? 'page' : undefined}>
    <HomeIcon name={item.icon} /><span>{item.label}</span>
  </a>)}</nav>;
}

function Track() {
  return <div className="concept-track" aria-hidden="true"><div dangerouslySetInnerHTML={{ __html: trackMarkup }} /><span>Circuit of the Americas</span></div>;
}

function RaceCard() {
  return <section className="concept-race" aria-labelledby="concept-race-title">
    <div className="race-copy">
      <div className="race-meta"><span>Практика 1</span><span>Этап 19 / 24</span></div>
      <h2 id="concept-race-title"><a href={weekend}>United States<br />Grand Prix <span aria-hidden="true">↗</span></a></h2>
      <p className="race-place">Остин, США · 23–25 октября</p>
      <div className="race-start"><div><span>Ближайшая сессия</span><strong>Сегодня, 20:30 <small>МСК</small></strong></div><div><span>До старта</span><strong>5 ч 30 мин</strong></div></div>
    </div><Track />
  </section>;
}

function Schedule() {
  return <section className="concept-schedule content-surface" aria-labelledby="schedule-title"><header className="section-head"><h2 id="schedule-title">Расписание</h2><span>МСК · UTC+3</span></header>
    <ol>{schedule.map((session, index) => <li key={session.name} className={index === 0 ? 'next-session' : undefined}><a href={weekend}>
      <span className="session-icon"><HomeIcon name={session.icon} /></span><span className="session-copy"><strong>{session.name}</strong><small>{session.day}{index === 0 ? ' · ближайшая' : ''}</small></span><time dateTime={session.iso}>{session.time}</time>
    </a></li>)}</ol><a href={weekend} className="section-link">Весь уик-энд <HomeIcon name="chevronRight" /></a>
  </section>;
}

function Personal() {
  return <section className="concept-personal content-surface" aria-labelledby="personal-title"><span className="personal-symbol"><HomeIcon name="predictions" /></span><div><h2 id="personal-title">Ваш прогноз на гонку</h2><p>Приём до 25 октября, 23:00 МСК</p></div><a href="/predictions" className="primary-action">Сделать прогноз <span aria-hidden="true">↗</span></a></section>;
}

function Standing({ title, rows, href }: { title: string; rows: typeof drivers; href: string }) {
  return <section className="concept-standing content-surface"><header className="section-head"><h3>{title}</h3><a href={href} aria-label={`Весь зачёт: ${title.toLowerCase()}`}><span>Весь зачёт</span><HomeIcon name="chevronRight" /></a></header>
    <ol>{rows.map((driver, i) => <li key={driver.name}><span className="standing-position">{String(i + 1).padStart(2, '0')}</span><span><strong>{driver.name}</strong><small>{driver.team}</small></span><strong className="standing-points">{driver.points}<small>очков</small></strong></li>)}</ol>
  </section>;
}

function Concept({ variant }: { variant: Variant }) {
  const [showTop, setShowTop] = useState(false);
  useEffect(() => {
    const scroll = () => setShowTop(window.scrollY > 260);
    window.addEventListener('scroll', scroll, { passive: true });
    return () => window.removeEventListener('scroll', scroll);
  }, []);
  return <div className={`concept concept-${variant}${query.get('glass') === 'off' ? ' solid-controls' : ''}`} id="overview">
    <a className="concept-skip" href="#concept-main">К содержимому</a>
    <aside className="concept-sidebar glass"><Brand /><p className="sidebar-label">Ваш гоночный мир</p><NavLinks /><div className="sidebar-secondary"><p className="sidebar-label">Чемпионат</p><a href="/drivers"><HomeIcon name="drivers" />Пилоты</a><a href="/constructors"><HomeIcon name="teams" />Команды</a><a href="/race-results"><HomeIcon name="results" />Результаты</a><p className="sidebar-label">Вне трассы</p><a href="/community"><HomeIcon name="social" />Сообщество</a><a href="/reaction-game"><HomeIcon name="reaction" />Игры</a></div><div className="sidebar-season">Сезон 2026<span>Независимый проект</span></div></aside>
    <header className="concept-toolbar glass"><Brand /><div className="panorama-nav"><NavLinks /></div><div className="toolbar-actions"><ThemeToggle /><a href="/notifications" className="icon-control" aria-label="Уведомления: 2 непрочитанных"><HomeIcon name="notifications" /><span className="notification-dot" /></a><a href="/profile" className="icon-control" aria-label="Мой профиль"><HomeIcon name="account" /></a></div></header>
    <main className="concept-main" id="concept-main" tabIndex={-1}>
      <header className="concept-heading"><div><p>Ваш гоночный уик-энд</p><h1>{variant === 'pitwall' ? 'Всё к старту.' : variant === 'panorama' ? 'Ближе к гонке.' : 'Обзор'}</h1></div><a href="/season" className="season-link">Сезон 2026 <span aria-hidden="true">↗</span></a></header>
      <div className="concept-event-grid"><RaceCard /><Personal /><Schedule /></div>
      <section className="concept-championship" aria-labelledby="championship-title"><header className="championship-heading"><h2 id="championship-title">В борьбе за титул</h2><span>Чемпионат 2026</span></header><div className="concept-standings"><Standing title="Пилоты" rows={drivers} href="/drivers" /><Standing title="Команды" rows={teams} href="/constructors" /></div></section>
      <details className="concept-more content-surface"><summary><span><HomeIcon name="games" />Вне трассы</span><HomeIcon name="chevronDown" /></summary><div><a href="/reaction-game"><HomeIcon name="reaction" />Тест реакции</a><a href="/history"><HomeIcon name="history" />История сезонов</a><a href="/community"><HomeIcon name="social" />С друзьями</a></div></details>
      <footer className="concept-footer"><span>TurboTears · независимый проект</span><span>Макет · данные вымышлены · 23.10.2026, 15:00 МСК</span></footer>
    </main>
    {showTop && <button className="concept-to-top glass" type="button" aria-label="Наверх" onClick={() => { window.scrollTo({ top: 0, behavior: 'instant' }); document.getElementById('concept-main')?.focus({ preventScroll: true }); }}><span aria-hidden="true">↑</span></button>}
    <div className="concept-bottom glass"><NavLinks mobile /></div>
  </div>;
}

function DeviceFrame({ mobile, src }: { mobile?: boolean; src: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const width = mobile ? 390 : 1200;
  const height = mobile ? 844 : 1000;
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => setScale(Math.min(1, entry.contentRect.width / width)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, [width]);
  return <section className={mobile ? 'device-column phone-column' : 'device-column'}><header><h3>{mobile ? 'Мобильная версия' : 'Десктоп'}</h3><a href={src} target="_blank" rel="noreferrer">Открыть отдельно ↗</a></header><div ref={container} className={`device-frame${mobile ? ' phone-frame' : ''}`} style={{ height: height * scale }}><iframe title={mobile ? 'Главная — телефон, 390 px' : 'Главная — десктоп, 1200 px'} src={src} style={{ width, height, transform: `scale(${scale})` }} /></div></section>;
}

export function Gallery() {
  const [variant, setVariant] = useState<Variant>(initialVariant);
  const [solid, setSolid] = useState(false);
  const [largeText, setLargeText] = useState(false);
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => 'light');
  const info = variants[variant];
  const src = `/tests/home-glass-options.html?view=screen&variant=${variant}&theme=${theme}${solid ? '&glass=off' : ''}${largeText ? '&scale=2' : ''}`;
  return <main className="options-gallery"><header className="gallery-heading"><div><p>TurboTears · дизайн главной</p><h1>Три взгляда на ваш уик-энд.</h1><p>Выберите композицию. Слева — десктоп, справа — телефон. Обе версии интерактивны.</p></div><ThemeToggle /></header>
    <fieldset className="variant-picker"><legend>Вариант главной страницы</legend>{(Object.keys(variants) as Variant[]).map((key, i) => <label key={key} className={variant === key ? 'selected' : ''}><input type="radio" name="variant" value={key} checked={variant === key} onChange={() => { setVariant(key); history.replaceState(null, '', `?variant=${key}`); }} /><span>{String(i + 1).padStart(2, '0')}</span><strong>{variants[key].name}</strong></label>)}</fieldset>
    <section className="gallery-description" aria-live="polite"><div><h2>{info.lead}</h2><p>{info.description}</p></div><div className="preview-settings"><label><input type="checkbox" checked={solid} onChange={event => setSolid(event.target.checked)} />Без прозрачности</label><label><input type="checkbox" checked={largeText} onChange={event => setLargeText(event.target.checked)} />Текст 200%</label></div></section>
    <div className="device-grid"><DeviceFrame src={src} /><DeviceFrame mobile src={src} /></div>
    <footer className="gallery-notes"><p><strong>Liquid Glass — в управлении.</strong> Плавающие панели пропускают цвет и размывают фон. Карточки, расписание и зачёт остаются непрозрачными. На сайте это CSS-адаптация материала Apple.</p><p>Варианты композиции — предложения для TurboTears. Ориентиры: <a href="https://developer.apple.com/design/human-interface-guidelines/materials">Apple HIG · Materials</a>, <a href="https://github.com/dickwu/apple-design-skill">Apple Design Skill</a> и <a href="https://www.w3.org/TR/WCAG22/">WCAG 2.2 AA</a>. Макеты не являются подтверждением полного соответствия.</p><a href="/tests/home-design-preview.html?auth=member">Сравнить с текущей главной ↗</a></footer>
  </main>;
}

initializeTheme();
const requestedTheme = query.get('theme');
if (requestedTheme === 'light' || requestedTheme === 'dark') setTheme(requestedTheme);
if (isScreen && query.get('scale') === '2') document.documentElement.style.fontSize = '200%';
const root = createRoot(document.getElementById('root')!);
root.render(isScreen ? <Concept variant={initialVariant} /> : <Gallery />);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());
