import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { avatarUrl, type Avatar, type AvatarOptions } from './avatar';
import './avatar-editor.css';

export default function AvatarEditor({ value, options, onSave, onClose }: {
  value: Avatar; options: AvatarOptions; onSave: (avatar: Avatar) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  async function save() {
    setBusy(true); setError('');
    try {
      await apiRequest('/api/profiles/me/avatar', draft, 'PATCH');
      onSave(draft);
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось сохранить аватар. Попробуйте ещё раз.'); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="avatar-editor" aria-labelledby="avatar-editor-title"
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header><div><p>ТВОЙ ОБРАЗ НА СТАРТЕ</p><h2 id="avatar-editor-title">Гараж аватаров</h2></div>
      <button type="button" aria-label="Закрыть конструктор аватара" disabled={busy} onClick={onClose}>×</button></header>
    <div className="avatar-editor-layout"><div className="avatar-editor-preview">
      <img src={avatarUrl(draft)} alt="Предпросмотр выбранного гонщика" width="384" height="384" />
      <span>ТВОЙ ГОНЩИК · ТВОИ ЦВЕТА</span><p>Вымышленные пилоты, вдохновлённые миром гонок.</p>
    </div><div className="avatar-editor-options">{(['helmet', 'suit', 'background'] as const).map(key =>
      <fieldset key={key} disabled={busy}><legend>{{ helmet: '01 / Шлем', suit: '02 / Комбинезон', background: '03 / Фон' }[key]}</legend>
        <div>{Object.entries(options[key]).map(([id, label]) => <button type="button" key={id}
          aria-pressed={draft[key] === id} onClick={() => { setDraft({ ...draft, [key]: id }); setError(''); }}>
          <img src={avatarUrl({ ...draft, [key]: id })} alt="" width="64" height="64" loading="lazy" />
          <span>{label}</span>{draft[key] === id && <b aria-hidden="true">✓</b>}
        </button>)}</div>
      </fieldset>)}</div></div>
    {error && <p role="alert" className="avatar-editor-error">{error}</p>}
    <footer><p>Шлем, комбинезон и фон выбираются независимо.</p><div>
      <button type="button" disabled={busy} onClick={onClose}>Отмена</button>
      <button type="button" className="avatar-editor-save" disabled={busy} onClick={() => void save()}>{busy ? 'Сохраняем…' : 'Сохранить аватар'}</button>
    </div></footer>
  </dialog>;
}
