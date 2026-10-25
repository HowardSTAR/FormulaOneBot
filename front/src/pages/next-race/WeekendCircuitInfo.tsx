import type { CircuitInsights } from '../../assets/circuitInsightsRu';
import { GlossaryText } from '../../components/GlossaryText';
import { profileDate, ratingTone, type CircuitProfile } from './circuit-profile';
import { TyreIllustration, type TyreKind } from './TyreIllustration';
import './weekend-circuit-info.css';

export function WeekendCircuitStats({ insights, limit }: { insights: CircuitInsights; limit?: number }) {
  return <dl className="weekend-stats">{insights.stats.slice(0, limit).map(stat => <div key={stat.label}>
    <dt>{stat.label}</dt><dd>{stat.value}{stat.hint && <small>{stat.hint}</small>}</dd>
  </div>)}</dl>;
}

function CircuitSymbol({ name }: { name: 'trophy' | 'helmet' | 'track' | 'clock' }) {
  return <svg className="circuit-info-symbol" width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === 'trophy' ? <><path d="M10 5h12v8a6 6 0 0 1-12 0V5Zm6 14v7m-5 1h10M10 8H5v4a5 5 0 0 0 5 5m12-9h5v4a5 5 0 0 1-5 5" /></>
      : name === 'helmet' ? <><path d="M5 18a11 11 0 1 1 22 0v7H12l-7-7Zm1-2h20M17 16l2 5h8M9 25l2 3h14" /></>
      : name === 'track' ? <path d="M8 7h17c6 0 5 8 0 8h-6l-3 8c-2 5-10 4-10-1V11c0-3 1-4 2-4Z" />
      : name === 'clock' ? <><circle cx="16" cy="18" r="11" /><path d="M16 7V3m-4 0h8m4 7 3-3M16 12v7l4 3" /></>
      : null}
  </svg>;
}

function CircuitRecords({ profile }: { profile: CircuitProfile }) {
  const records = [profile.team && { ...profile.team, label: 'Самая успешная команда', symbol: 'trophy' as const }, profile.driver && { ...profile.driver, label: 'Самый успешный пилот', symbol: 'helmet' as const }].filter(record => !!record);
  return <section className="circuit-records" aria-label="История и рекорды трассы">
    {records.map(record => <div className="circuit-record-row" key={record.label}>
      <div className="circuit-win-count"><strong>{String(record.wins).padStart(2, '0')}</strong><span>Побед</span></div>
      <div className="circuit-record-person"><CircuitSymbol name={record.symbol} /><span>{record.label}</span><strong>{record.name}</strong></div>
    </div>)}
    {profile.firstRace && <p className="circuit-history-note">Гонки на этой трассе · {profile.firstRace}–{profile.historyThrough}</p>}
    {profile.firstRace && <div className="circuit-detail-row"><CircuitSymbol name="track" /><dl>
      {profile.opened && <div><dt>Открыта</dt><dd>{profile.opened}</dd></div>}
      <div><dt>Первая гонка F1</dt><dd>{profile.firstRace}</dd></div>
    </dl></div>}
    {profile.lapRecord && <div className="circuit-detail-row"><CircuitSymbol name="clock" /><dl><div><dt>Быстрейший круг с 2004 года<small>Включая прежние конфигурации</small></dt><dd>{profile.lapRecord.time}<small>{profile.lapRecord.year}</small></dd></div><div><dt>Пилот</dt><dd>{profile.lapRecord.driver}</dd></div></dl></div>}
    {profile.pitLoss && <div className="circuit-detail-row"><CircuitSymbol name="clock" /><dl><div><dt>Потеря на пит-стопе</dt><dd>{profile.pitLoss}</dd></div><div><dt>Источник</dt><dd className="circuit-detail-text">Данные Pirelli</dd></div></dl></div>}
  </section>;
}

function TyreCard({ kind, code, label }: { kind: TyreKind; code: string; label: string }) {
  return <div className={`circuit-compound circuit-compound--${kind}`}>
    <TyreIllustration kind={kind} /><strong>{code}</strong><span>{label}</span>
  </div>;
}

export function WeekendCircuitInfo({ insights, profile, season, loading = false, error = false, retry }: { insights: CircuitInsights; profile: CircuitProfile | null; season: number; loading?: boolean; error?: boolean; retry?: () => void }) {
  return <section className="weekend-circuit-info" aria-label="Характеристики и особенности трассы">
    {loading ? <p className="circuit-source-note" role="status">Загружаем данные Pirelli…</p> : error ? <div className="circuit-profile-error" role="status"><p>Не удалось загрузить профиль трассы.</p><button className="weekend-secondary" type="button" onClick={retry}>Повторить загрузку</button></div> : !profile?.compounds.length && <p className="circuit-source-note">Данные Pirelli на этот этап ({season}) пока недоступны.</p>}
    {profile && <>
      {profile.compounds.length === 3 && <div className="circuit-compounds" aria-label={`Составы шин на этап ${profile.season}`}>
        {profile.compounds.map((compound, index) => <TyreCard key={compound} kind={(['hard', 'medium', 'soft'] as const)[index]} code={compound} label={['Hard', 'Medium', 'Soft'][index]} />)}
      </div>}
      {profile.ratings.length > 0 ? <>
        <dl className="circuit-ratings" aria-label="Характеристики трассы по шкале Pirelli">
          {profile.ratings.map(rating => <div key={rating.label} data-level={ratingTone(rating.value)}><dt>{rating.label}</dt><dd><strong>{rating.value}<small>/5</small></strong><meter min="0" max="5" value={rating.value} aria-label={`${rating.label}: ${rating.value} из 5`} /></dd></div>)}
        </dl>
        <p className="circuit-source-note">Pirelli Motorsport · {profileDate(profile.ratingPublished || profile.published)}{profile.stale && ' · последнее проверенное обновление'}</p>
      </> : <p className="circuit-source-note">Характеристики появятся после обработки инфографики Pirelli.</p>}
      <CircuitRecords profile={profile} />
    </>}
    {season >= 2022 && <details className="circuit-tyre-details"><summary>Шины для дождя и давление</summary><div>
      <div className="circuit-compounds circuit-compounds--rain" aria-label="Дождевые типы шин">
        <TyreCard kind="intermediate" code="Intermediate" label="Влажная трасса · зелёные" />
        <TyreCard kind="wet" code="Full Wet" label="Сильный дождь · синие" />
      </div>
      <p>Слики — для сухой трассы. Intermediate и Full Wet имеют разный протектор для отвода воды. Их маркировка не зависит от выбранных на этап составов C.</p>
      {profile?.pressures ? <><dl className="circuit-pressure"><div><dt>Передние · старт</dt><dd>{profile.pressures.front}</dd></div><div><dt>Задние · старт</dt><dd>{profile.pressures.rear}</dd></div></dl><p className="circuit-source-note">Минимальное стартовое давление сликов · Pirelli, {profileDate(profile.ratingPublished || profile.published)}. Может уточняться по ходу уик-энда.</p></> : <p className="circuit-source-note">Давление для выбранного этапа пока не подтверждено.</p>}
    </div></details>}
    <section className="circuit-extra-facts" aria-label="Дополнительные сведения о трассе">
      <h2>О трассе</h2><WeekendCircuitStats insights={insights} />
      {insights.facts.length > 0 && <div className="weekend-facts">{insights.facts.map(fact => <details key={fact.title}>
        <summary>{fact.title}</summary><p><GlossaryText>{fact.text}</GlossaryText></p>
      </details>)}</div>}
    </section>
    {profile && profile.sources.length > 0 && <details className="circuit-sources"><summary>Источники данных</summary><ul>{profile.sources.map(source => <li key={source.href}><a href={source.href} target="_blank" rel="noreferrer">{source.title}</a></li>)}</ul></details>}
  </section>;
}
