import { Link, useSearchParams } from 'react-router-dom';
import { HomeIcon } from './HomeIcon';
import SupporterBadge from '../../components/SupporterBadge';
import { GlassSwitch } from './GlassSwitch';
import { homeSectionPath } from '../../helpers/homeSections';
import './home-sections.css';
import { sections, useHomeSection, type HomeSection } from './home-section-model';

type FeatureSection = Exclude<HomeSection, 'season'>;
const track = `${import.meta.env.BASE_URL}race-game/assets/emerald-loop-track.png`;

export function HomeSections() {
  const [params] = useSearchParams();
  const active = useHomeSection();
  return <GlassSwitch className="home-sections" label="Разделы главной" selected={active} items={sections.map(section => ({ ...section, to: homeSectionPath(section.id, params) }))} />;
}

/* These previews describe the destination; they never display invented player data. */
function GamePreview({ game }: { game: 'reaction' | 'grid' | 'arcade' }) {
  if (game === 'reaction') return <div className="home-media-preview home-game-preview home-game-preview--lights" aria-hidden="true">{Array.from({ length: 4 }, (_, column) => <span key={column}>{Array.from({ length: 4 }, (_, lamp) => <i key={lamp} />)}</span>)}</div>;
  if (game === 'grid') return <div className="home-media-preview home-game-preview home-game-preview--grid" aria-hidden="true">{Array.from({ length: 9 }, (_, tile) => <i key={tile} />)}</div>;
  return <div className="home-media-preview home-game-preview home-game-preview--track" aria-hidden="true"><img src={track} alt="" width="512" height="512" loading="lazy" /></div>;
}

export function HomeSectionHero({ section }: { section: FeatureSection }) {
  const games = section === 'games', guide = section === 'guide';
  const title = games ? 'Ваш прогноз. Следующий подиум.' : guide ? 'Что улучшим в TurboTears?' : 'Больше своего в TurboTears.';
  const text = games ? 'Выберите свою тройку на гонку и соревнуйтесь с друзьями в зачёте прогнозов.' : guide ? 'Расскажите, чего не хватает, предложите идею или сообщите об ошибке.' : 'Поддержите проект, присоединитесь к клубному зачёту и откройте оформление профиля.';
  return <section className={`home-section-hero home-section-hero--${section}`} aria-labelledby={`home-banner-title-${section}`}>
    <div className="home-banner-copy"><h2 id={`home-banner-title-${section}`}>{title}</h2><p>{text}</p>
      {section === 'subscription' ? <a className="home-glass-button home-glass-button--primary" href="https://boosty.to/turbotears" target="_blank" rel="noopener noreferrer">Подписаться на Boosty<HomeIcon name="chevronRight" /></a> : <Link className="home-glass-button home-glass-button--primary" to={games ? '/predictions' : '/contact-admin'}>{games ? 'Сделать прогноз' : 'Написать отзыв'}<HomeIcon name="chevronRight" /></Link>}
    </div>
    {games ? <div className="home-banner-art home-podium-preview" aria-hidden="true"><span>2</span><span>1</span><span>3</span></div> : guide ? <div className="home-banner-art home-feedback-art" aria-hidden="true"><span>Есть идея?</span><HomeIcon name="contact" /></div> : <div className="home-banner-art home-member-preview" aria-hidden="true"><div><HomeIcon name="account" /><span>TurboTears<SupporterBadge tierName="Свой стиль" /></span></div><span>Пример оформления профиля</span></div>}
  </section>;
}

type GuidePreviewKind = 'history' | 'wiki' | 'weekend';
function GuidePreview({ kind }: { kind: GuidePreviewKind }) {
  const words = kind === 'history' ? ['1950', String(new Date().getFullYear())] : kind === 'wiki' ? ['DRS', 'Пит-стоп', 'Слипстрим'] : ['FP', 'Q', 'GP'];
  return <div className={`home-media-preview home-guide-preview home-guide-preview--${kind}`} aria-hidden="true">{words.map(word => <span key={word}>{word}</span>)}</div>;
}
function GuideLink({ to, title, text, preview }: { to: string; title: string; text: string; preview: GuidePreviewKind }) {
  return <Link to={to} className={`home-media-tile home-guide-link home-guide-link--${preview}`}><GuidePreview kind={preview} /><div className="home-media-caption"><div><strong>{title}</strong><p>{text}</p></div><span className="home-media-enter"><HomeIcon name="chevronRight" /></span></div></Link>;
}

function MembershipPreview({ level }: { level: 'club' | 'style' | 'full' }) {
  return <div className={`home-media-preview home-membership-preview home-membership-preview--${level}`} aria-hidden="true">
    {level === 'club' ? <SupporterBadge large tierName="На старт" /> : <>{(level === 'style' ? ['red', 'silver'] : ['gold', 'neon']).map(frame => <span key={frame} className={`home-preview-avatar home-preview-avatar--${frame}`}><HomeIcon name="account" /></span>)}</>}
  </div>;
}

export function HomeSectionContent({ section }: { section: FeatureSection }) {
  if (section === 'games') return <section className="home-section-content" aria-labelledby="home-section-title"><header><h2 id="home-section-title">Между гонками</h2><p>Три способа проверить скорость.</p></header><div className="home-game-banners">
    {([
      ['reaction', '/reaction-game', 'Тест реакции', 'Погасли огни — ваш старт.'],
      ['grid', '/reflex-grid-game', 'Reflex Grid', 'Ловите плитки. Держите ритм.'],
      ['arcade', '/race-game', 'Emerald Loop', 'На трассу за быстрым кругом.'],
    ] as const).map(([game, to, title, text]) => <Link key={game} className={`home-media-tile home-game-banner home-game-banner--${game}`} to={to}><GamePreview game={game} /><span className="home-media-caption home-game-caption"><span><strong>{title}</strong><small>{text}</small></span><span className="home-media-enter home-game-enter"><HomeIcon name="chevronRight" /></span></span></Link>)}
  </div></section>;
  if (section === 'guide') return <section className="home-section-content" aria-labelledby="home-section-title"><header><h2 id="home-section-title">Разобраться в Формуле-1</h2><p>От первого уик-энда до истории чемпионата.</p></header><div className="home-guide-links">
    <GuideLink to="/history" title="История чемпионата" text="Сезоны, пилоты и команды. Посмотрите, как менялась борьба за титул." preview="history" />
    <GuideLink to="/wiki" title="Справочник F1" text="Термины, правила и устройство болида." preview="wiki" />
    <GuideLink to="/wiki?term=race-weekend" title="Вики уик-энда" text="Практики, квалификация и гонка." preview="weekend" />
  </div></section>;
  return <section className="home-section-content home-membership" aria-labelledby="home-section-title"><header><h2 id="home-section-title">Что даёт подписка</h2><p>Каждый следующий уровень включает преимущества предыдущего.</p></header><div className="home-membership-levels">
    {([
      ['club', 'На старт', 'Значок в профиле и таблице прогнозов. Участие в общем зачёте клуба TurboTears.'],
      ['style', 'Свой стиль', 'Красная и серебряная рамки, красный и синий ник. Фоны «Стартовая решётка» и «Алый».'],
      ['full', 'Полный газ', 'Золотая и неоновая рамки, золотой и мятный ник. Фоны «Сияние» и «Чемпион».'],
    ] as const).map(([level, title, text]) => <section className={`home-media-tile home-member-level home-member-level--${level}`} key={level} aria-labelledby={`home-level-${level}`}><MembershipPreview level={level} /><div className="home-media-caption"><div><h3 id={`home-level-${level}`}>{title}</h3><p>{text}</p></div></div></section>)}
  </div><div className="home-membership-footer"><p>Уже подписаны? Используйте одинаковый подтверждённый email на сайте и Boosty.</p><Link className="home-glass-button" to="/account">Проверить свою подписку<HomeIcon name="chevronRight" /></Link></div></section>;
}
