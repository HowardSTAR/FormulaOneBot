import { Fragment, useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { TROPHY_BADGE_CHANGED, TROPHY_UPDATED, trophyImage, type TrophyAward, type TrophyCollection, type TrophyFamily, type TrophyLevel } from '../../helpers/trophies';
import './trophies.css';

function Medal({ family, level }: { family: string; level: number }) {
  return <img src={trophyImage(family, level)} alt="" width="256" height="256" loading="lazy" />;
}

export default function ProfileTrophies({ userId, owner, onBadge }: { userId: number; owner: boolean; onBadge: (badge: TrophyAward | null) => void }) {
  const [data, setData] = useState<TrophyCollection | null>(null);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [active, setActive] = useState('oracle'), [levels, setLevels] = useState<Record<string,number>>({});
  const [mode, setMode] = useState<'collection' | 'badge'>('collection');
  const [draft, setDraft] = useState<string | null>(null), [busy, setBusy] = useState(false);
  useEffect(() => {
    let valid = true;
    const apply = (value: TrophyCollection) => {
      if (!valid || !Array.isArray(value.families) || value.user_id !== userId) return;
      setData(value); onBadge(value.badge);
      setDraft(value.badge?.id || null);
    };
    const update = (event: Event) => { if (owner) apply((event as CustomEvent<TrophyCollection>).detail); };
    void apiRequest<TrophyCollection>(`/api/profiles/${owner ? 'me' : userId}/trophies`).then(apply)
      .catch(() => { if (valid) setError('Не удалось загрузить трофеи. Обновите страницу, чтобы повторить.'); });
    window.addEventListener(TROPHY_UPDATED, update);
    return () => { valid = false; window.removeEventListener(TROPHY_UPDATED, update); };
  }, [userId, owner, onBadge]);
  const families = data?.families || [];
  const selected = families.find(family => family.id === active) || families[0];
  function levelFor(family: TrophyFamily) {
    return family.levels.find(level => level.level === levels[family.id])
      || [...family.levels].reverse().find(level => level.earned_at) || family.levels[0];
  }
  function select(family: TrophyFamily, level: TrophyLevel) {
    setActive(family.id); setLevels(previous => ({ ...previous, [family.id]: level.level }));
  }
  async function saveBadge() {
    if (!data) return;
    setBusy(true); setNotice('');
    try {
      await apiRequest('/api/profiles/me/trophy-badge', { id: draft }, 'PATCH');
      const badge = data.earned.find(award => award.id === draft) || null;
      setData({ ...data, badge }); onBadge(badge);
      window.dispatchEvent(new CustomEvent(TROPHY_BADGE_CHANGED, { detail: { userId, badge } }));
      setNotice(badge ? 'Бейдж профиля сохранён' : 'Бейдж убран');
    } catch (e) { setNotice(e instanceof Error ? e.message : 'Не удалось сохранить бейдж'); }
    finally { setBusy(false); }
  }
  function details(family: TrophyFamily, compact = false) {
    const level = levelFor(family);
    const earned = Boolean(level.earned_at);
    const progress = level.progress || 0;
    return <div className={compact ? 'trophy-details trophy-details-mobile' : 'trophy-details'}>
      {compact && <div className="trophy-detail-heading"><Medal family={family.id} level={level.level} /><div><span>{family.group} · {level.tier}</span><h3>{family.name}</h3></div></div>}
      <div className="trophy-tier-controls" aria-label={`Уровни: ${family.name}`}>{family.levels.map(item => <button key={item.level} type="button" aria-pressed={item.level === level.level} onClick={() => select(family,item)}>{item.tier}</button>)}</div>
      <p className="trophy-level-label">{level.tier} · {level.level + 1} / 3{level.season > 0 && ` · ${level.season}`}</p>
      {!compact && <h3>{family.name}</h3>}
      {owner ? <><p className="trophy-condition">{level.condition}</p>
        <div className="trophy-progress" role="progressbar" aria-label={`${family.name}, ${level.tier}`} aria-valuemin={0} aria-valuemax={level.target || 1} aria-valuenow={Math.min(progress,level.target || 1)}>
          <i style={{ width: `${earned ? 100 : level.target ? Math.min(100,progress / level.target * 100) : 0}%` }} /></div>
        <div className="trophy-progress-copy"><span>{earned ? '✓ Условие выполнено' : `${progress} / ${level.target ?? '—'}`}</span><span>{earned ? 'Получен' : family.id === 'rhythm' && level.level === 2 && level.target && progress >= level.target && !data?.season_closed ? 'Ждём конца сезона' : 'В процессе'}</span></div>
        <details><summary>ⓘ Что засчитывается</summary><p>{level.rule}</p></details>
        <button className="trophy-equip" type="button" disabled={!earned} onClick={() => { setDraft(level.id); setMode('badge'); }}>{data?.badge?.id === level.id ? '✓ Бейдж профиля' : earned ? 'Сделать бейджем' : 'Сначала откройте трофей'}</button></>
        : <p className="trophy-earned-date">Получен {new Date(`${level.earned_at?.replace(' ','T')}Z`).toLocaleDateString('ru-RU')}{level.season > 0 && ` · сезон ${level.season}`}</p>}
    </div>;
  }
  const selectedRow = Math.floor(families.indexOf(selected) / 3);
  return <section className="profile-trophies profile-panel" id="profile-trophies" aria-labelledby="profile-trophies-title">
    <header className="trophy-heading"><div><p>КОЛЛЕКЦИЯ TURBOTEARS</p><h2 id="profile-trophies-title">Трофеи</h2><span>{owner ? `${data?.earned.length ?? '—'} получено · 8 семейств` : `${data?.earned.length ?? '—'} получено`}</span></div>
      {owner && <nav aria-label="Коллекция и бейдж"><button type="button" aria-pressed={mode === 'collection'} onClick={() => setMode('collection')}>Коллекция</button><button type="button" aria-pressed={mode === 'badge'} onClick={() => { setDraft(data?.badge?.id || null); setMode('badge'); }}>Бейдж профиля</button></nav>}</header>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">Загружаем трофеи…</p>}
    {data && mode === 'collection' && <>
      {owner && <p className="trophy-hint">Бронза, серебро и золото. Свайп меняет уровень, нажатие открывает условие.</p>}
      {owner && !data.calendar_known && <p className="profile-muted">Календарь сезона уточняется. Цели за половину и весь сезон появятся после обновления расписания.</p>}
      <div className="trophy-grid">{families.map((family,index) => {
        const level = levelFor(family);
        return <Fragment key={family.id}><article className={`trophy-card${family.id === selected?.id ? ' is-active' : ''}`} data-family={family.id}>
          <div className="trophy-card-status"><span>{family.group}</span><span>{level.earned_at ? '✓ Получен' : 'Не открыт'}</span></div>
          <button type="button" className="trophy-art" aria-label={`${family.name}, ${level.tier}: показать условие`} onClick={() => setActive(family.id)}
            onTouchStart={event => { event.currentTarget.dataset.touchX=String(event.touches[0].clientX); event.currentTarget.dataset.touchY=String(event.touches[0].clientY); }}
            onTouchEnd={event => { const x=Number(event.currentTarget.dataset.touchX),y=Number(event.currentTarget.dataset.touchY),dx=event.changedTouches[0].clientX-x,dy=event.changedTouches[0].clientY-y; if(Math.abs(dx)>25 && Math.abs(dx)>Math.abs(dy)*1.3){const i=family.levels.indexOf(level); select(family,family.levels[Math.max(0,Math.min(family.levels.length-1,i+(dx<0?1:-1)))]);} }}>
            <Medal family={family.id} level={level.level} /></button>
          <div className="trophy-mobile-title">{family.name}</div><div className="trophy-mobile-dots" aria-hidden="true">{family.levels.map(item => <i key={item.level} className={item.level === level.level ? 'is-active' : ''} />)}</div>
          <div className="trophy-desktop-details">{details(family)}</div>
        </article>{selected && (index === families.length-1 || index % 3 === 2) && Math.floor(index/3) === selectedRow && details(selected,true)}</Fragment>;
      })}</div>
      {!data.earned.length && !owner && <p className="profile-muted">Первые трофеи ещё впереди.</p>}
      {data.earned.some(award => award.season > 0 && award.season !== data.season) && <div className="trophy-season-archive"><h3>Предыдущие сезоны</h3><div>{data.earned.filter(award => award.season > 0 && award.season !== data.season).map(award => <span key={award.id}><Medal family={award.family} level={award.level} />{award.tier} · {award.season}</span>)}</div></div>}
      {owner && <p className="trophy-hint">Полученные награды сохраняются навсегда. Поддержка — отдельная необязательная ветка.</p>}
    </>}
    {data && mode === 'badge' && <div className="trophy-badge-editor"><p>Один знак рядом с именем. Можно выбрать любой полученный уровень.</p>
      <div className="trophy-badge-picks">{data.earned.map(award => <button key={award.id} type="button" aria-pressed={draft === award.id} disabled={busy} onClick={() => setDraft(award.id)}><Medal family={award.family} level={award.level} /><span>{award.name}<small>{award.tier}{award.season > 0 && ` · ${award.season}`}</small></span></button>)}</div>
      <button type="button" className="trophy-none" aria-pressed={draft === null} disabled={busy} onClick={() => setDraft(null)}>Без бейджа</button>
      <button type="button" className="profile-primary" disabled={busy || draft === (data.badge?.id || null)} onClick={() => void saveBadge()}>{busy ? 'Сохраняем…' : 'Сохранить бейдж'}</button>
    </div>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
