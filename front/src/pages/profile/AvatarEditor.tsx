import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { avatarUrl, type Avatar, type AvatarOptions } from './avatar';
import AvatarImage from './AvatarImage';
import './avatar-editor.css';

export type ProfileStyle = { frame: string; color: string; background: string };
export type ProfileStyleOptions = Record<keyof ProfileStyle, Record<string, number>>;
const labels: Record<string, string> = { classic: 'Классика', red: 'Красный', silver: 'Серебро', gold: 'Золото', neon: 'Неон', white: 'Белый', blue: 'Синий', mint: 'Мятный', carbon: 'Карбон', grid: 'Стартовая решётка', scarlet: 'Алый', aurora: 'Сияние', champion: 'Чемпион' };

export default function AvatarEditor({ value, options, style, styleOptions, tier, onAvatarSave, onStyleSave, onClose }: {
  value: Avatar; options: AvatarOptions; style: ProfileStyle; styleOptions: ProfileStyleOptions; tier: number;
  onAvatarSave: (avatar: Avatar) => void; onStyleSave: (style: ProfileStyle) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState(value);
  const [styleDraft, setStyleDraft] = useState(style);
  const [savedAvatar, setSavedAvatar] = useState(value);
  const [savedStyle, setSavedStyle] = useState(style);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [closing, setClosing] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(savedAvatar)
    || JSON.stringify(styleDraft) !== JSON.stringify(savedStyle);
  useEffect(() => {
    const element = dialog.current;
    const opener = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => {
    if (!closing) return;
    const handle = window.setTimeout(onClose, 180);
    return () => window.clearTimeout(handle);
  }, [closing, onClose]);
  function close() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) onClose();
    else setClosing(true);
  }
  async function save() {
    setBusy(true); setError('');
    let avatarSaved = false;
    try {
      if (JSON.stringify(draft) !== JSON.stringify(savedAvatar)) {
        await apiRequest('/api/profiles/me/avatar', draft, 'PATCH');
        setSavedAvatar(draft);
        onAvatarSave(draft);
        avatarSaved = true;
      }
      if (JSON.stringify(styleDraft) !== JSON.stringify(savedStyle)) {
        await apiRequest('/api/profiles/me/style', styleDraft, 'PATCH');
        setSavedStyle(styleDraft);
        onStyleSave(styleDraft);
      }
      close();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Не удалось сохранить изменения. Попробуйте ещё раз.';
      setError(avatarSaved ? `Аватар сохранён. Оформление пока не сохранено: ${message}` : message);
    }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className={`avatar-editor${closing ? ' avatar-editor-closing' : ''}`} aria-labelledby="avatar-editor-title"
    onCancel={event => { event.preventDefault(); if (!busy) close(); }}>
    <header><div><p>ТВОЙ ОБРАЗ НА СТАРТЕ</p><h2 id="avatar-editor-title">Аватар и оформление</h2></div>
      <button type="button" aria-label="Закрыть настройки аватара и оформления" disabled={busy || closing} onClick={close}>×</button></header>
    <div className="avatar-editor-layout"><div className="avatar-editor-preview">
      <AvatarImage src={avatarUrl(draft)} alt="Предпросмотр выбранного гонщика" />
      <span>ТВОЙ ГОНЩИК · ТВОИ ЦВЕТА</span><p>Вымышленные пилоты, вдохновлённые миром гонок.</p>
    </div><div className="avatar-editor-options">{(['helmet', 'suit', 'background'] as const).map(key =>
      <fieldset key={key} disabled={busy || closing}><legend>{{ helmet: '01 / Шлем', suit: '02 / Комбинезон', background: '03 / Фон' }[key]}</legend>
        <div>{Object.entries(options[key]).map(([id, label]) => <button type="button" key={id}
          aria-pressed={draft[key] === id} onClick={() => { setDraft({ ...draft, [key]: id }); setError(''); }}>
          <AvatarImage src={avatarUrl({ ...draft, [key]: id })} />
          <span>{label}</span>{draft[key] === id && <b aria-hidden="true">✓</b>}
        </button>)}</div>
      </fieldset>)}</div></div>
    <section className="avatar-editor-style" aria-labelledby="profile-style-title">
      <h3 id="profile-style-title">Твой стиль</h3>
      <p className="profile-muted">«Свой стиль» открывает рамки, цвета и фоны. «Полный газ» — всю коллекцию.</p>
      <div className="profile-customize">{(['frame', 'color', 'background'] as const).map(key => <fieldset key={key} disabled={busy || closing}>
        <legend>{{ frame: 'Рамка аватара', color: 'Цвет ника', background: 'Фон карточки' }[key]}</legend>
        {Object.entries(styleOptions[key]).map(([value, requiredTier]) => <button type="button" key={value}
          disabled={requiredTier > tier} aria-pressed={styleDraft[key] === value}
          title={requiredTier > tier ? `Доступно с уровня «${requiredTier === 3 ? 'Полный газ' : 'Свой стиль'}»` : labels[value]}
          onClick={() => { setStyleDraft({ ...styleDraft, [key]: value }); setError(''); }}>
          {labels[value]}{requiredTier > tier && ' · 🔒'}
        </button>)}
      </fieldset>)}</div>
    </section>
    <footer><p role={error ? 'alert' : undefined} className="avatar-editor-error">{error}</p><div>
      <button type="button" disabled={busy || closing} onClick={close}>Отмена</button>
      <button type="button" className="avatar-editor-save" disabled={busy || closing || !dirty} onClick={() => void save()}>{busy ? 'Сохраняем…' : 'Сохранить изменения'}</button>
    </div></footer>
  </dialog>;
}
