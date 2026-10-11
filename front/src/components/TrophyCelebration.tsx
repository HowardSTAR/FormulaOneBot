import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { trophyImage, type TrophyAward } from '../helpers/trophies';
import { hapticImpact } from '../helpers/telegram';
import './trophy-celebration.css';

export default function TrophyCelebration({ award, remaining, onAcknowledge }: {
  award: TrophyAward; remaining: number; onAcknowledge: (all: boolean) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    hapticImpact('light');
    return () => element?.close();
  }, []);
  async function accept(all = false) {
    if (busy) return;
    setBusy(true); setError('');
    try { await onAcknowledge(all); }
    catch { setError('Не удалось подтвердить просмотр. Трофей сохранён — попробуйте ещё раз.'); setBusy(false); }
  }
  return createPortal(<dialog ref={dialog} className="trophy-unlock" data-tier={award.level} aria-labelledby="trophy-unlock-title"
    aria-describedby="trophy-unlock-description" onCancel={event => { event.preventDefault(); void accept(); }}>
    <button type="button" className="trophy-unlock-close" disabled={busy} aria-label="Закрыть получение трофея" onClick={() => void accept()}>×</button>
    <p className="trophy-unlock-eyebrow">НОВОЕ ДОСТИЖЕНИЕ{remaining > 1 && ` · ЕЩЁ ${remaining - 1}`}</p>
    <div className="trophy-unlock-stage" aria-hidden="true"><span className="trophy-unlock-halo" />
      <div className="trophy-unlock-sparks">{Array.from({ length: 18 }, (_, i) => <i key={i} style={{ '--spark-angle': `${i * 20}deg`, '--spark-delay': `${i % 5 * 45}ms` } as CSSProperties} />)}</div>
      <img className="trophy-unlock-medal" src={trophyImage(award.family, award.level)} alt="" width="320" height="320" />
      <span className="trophy-unlock-shine" />
    </div>
    <p className="trophy-unlock-tier">{award.tier}{award.season > 0 && ` · СЕЗОН ${award.season}`}</p>
    <h2 id="trophy-unlock-title">{award.name}</h2>
    <p id="trophy-unlock-description">Твой новый трофей уже в коллекции.<br />Его можно выбрать бейджем профиля.</p>
    {error && <p className="trophy-unlock-error" role="alert">{error}</p>}
    <button type="button" className="trophy-unlock-primary" disabled={busy} onClick={() => void accept()}>{busy ? 'Сохраняем…' : remaining > 1 ? 'Следующий трофей →' : 'Забрать трофей'}</button>
    {remaining > 1 ? <button type="button" className="trophy-unlock-secondary" disabled={busy} onClick={() => void accept(true)}>Забрать все · {Math.min(remaining,60)}</button>
      : <a className="trophy-unlock-secondary" href="/profile#profile-trophies" onClick={event => { event.preventDefault(); if (busy) return; setBusy(true); void onAcknowledge(false).then(() => window.location.assign('/profile#profile-trophies')).catch(() => {setError('Не удалось подтвердить просмотр. Попробуйте ещё раз.');setBusy(false);}); }}>Открыть коллекцию</a>}
  </dialog>, document.body);
}
