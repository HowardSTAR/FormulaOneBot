import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { avatarUrl, type Avatar, type AvatarOptions } from './avatar';
import AvatarImage from './AvatarImage';
import { Link } from 'react-router-dom';
import { boostyCheckFailureLabel, boostySubscriptionLabel, type BoostyStatus } from '../../helpers/boosty';
import { checkBoostySubscription } from '../../helpers/boostyApi';
import './avatar-editor.css';

export type ProfileStyle = { frame: string; color: string; background: string };
export type ProfileStyleOptions = Record<keyof ProfileStyle, Record<string, number>>;
const labels: Record<string, string> = { classic: 'Классика', red: 'Красный', silver: 'Серебро', gold: 'Золото', neon: 'Неон', white: 'Белый', blue: 'Синий', mint: 'Мятный', carbon: 'Карбон', grid: 'Стартовая решётка', scarlet: 'Алый', aurora: 'Сияние', champion: 'Чемпион' };

export default function AvatarEditor({ value, options, style, styleOptions, tier, onAvatarSave, onStyleSave, onSubscriptionCheck, onClose }: {
  value: Avatar; options: AvatarOptions; style: ProfileStyle; styleOptions: ProfileStyleOptions; tier: number;
  onAvatarSave: (avatar: Avatar) => void; onStyleSave: (style: ProfileStyle) => void; onClose: () => void;
  onSubscriptionCheck: () => Promise<{ tier: number; style: ProfileStyle }>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState(value);
  const [styleDraft, setStyleDraft] = useState(style);
  const [savedAvatar, setSavedAvatar] = useState(value);
  const [savedStyle, setSavedStyle] = useState(style);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [closing, setClosing] = useState(false);
  const [subscription, setSubscription] = useState<BoostyStatus | null>(null);
  const [subscriptionLoading, setSubscriptionLoading] = useState(true);
  const [subscriptionBusy, setSubscriptionBusy] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState('');
  const locked = busy || closing || subscriptionBusy;
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
    let active = true;
    apiRequest<BoostyStatus>('/api/account/boosty').then(status => {
      if (active) setSubscription(status);
    }).catch(() => {
      if (active) setSubscriptionError('Не удалось загрузить статус подписки. Повторите проверку.');
    }).finally(() => { if (active) setSubscriptionLoading(false); });
    return () => { active = false; };
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
  async function checkSubscription() {
    setSubscriptionBusy(true); setSubscriptionError('');
    try {
      const status = await checkBoostySubscription();
      setSubscription(status);
      if (status.check_failed) return;
      try {
        const updated = await onSubscriptionCheck();
        // Preserve unsaved choices when upgrading, replace newly locked choices when downgrading.
        setStyleDraft(current => JSON.stringify(current) === JSON.stringify(savedStyle) ? updated.style : Object.fromEntries(Object.entries(current).map(([key, value]) => [key,
          styleOptions[key as keyof ProfileStyle][value] <= updated.tier ? value : updated.style[key as keyof ProfileStyle],
        ])) as ProfileStyle);
        setSavedStyle(updated.style);
      } catch {
        setSubscriptionError('Подписка проверена, но оформление не удалось обновить. Повторите проверку.');
      }
    } catch (reason) {
      setSubscriptionError(reason instanceof Error ? reason.message : 'Не удалось проверить подписку. Повторите позже.');
    } finally { setSubscriptionBusy(false); }
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
    onCancel={event => { event.preventDefault(); if (!locked) close(); }}>
    <header><div><p>ТВОЙ ОБРАЗ НА СТАРТЕ</p><h2 id="avatar-editor-title">Аватар и оформление</h2></div>
      <button type="button" aria-label="Закрыть настройки аватара и оформления" disabled={locked} onClick={close}>×</button></header>
    <div className="avatar-editor-layout"><div className="avatar-editor-preview">
      <AvatarImage src={avatarUrl(draft)} alt="Предпросмотр выбранного гонщика" />
      <span>ТВОЙ ГОНЩИК · ТВОИ ЦВЕТА</span><p>Вымышленные пилоты, вдохновлённые миром гонок.</p>
    </div><div className="avatar-editor-options">{(['helmet', 'suit', 'background'] as const).map(key =>
      <fieldset key={key} disabled={locked}><legend>{{ helmet: '01 / Шлем', suit: '02 / Комбинезон', background: '03 / Фон' }[key]}</legend>
        <div>{Object.entries(options[key]).map(([id, label]) => <button type="button" key={id}
          aria-pressed={draft[key] === id} onClick={() => { setDraft({ ...draft, [key]: id }); setError(''); }}>
          <AvatarImage src={avatarUrl({ ...draft, [key]: id })} />
          <span>{label}</span>{draft[key] === id && <b aria-hidden="true">✓</b>}
        </button>)}</div>
      </fieldset>)}</div></div>
    <section className="avatar-editor-style" aria-labelledby="profile-style-title">
      <h3 id="profile-style-title">Твой стиль</h3>
      <p className="profile-muted">«Свой стиль» и «Полный газ» — уровни подписки TurboTears на Boosty. «Свой стиль» открывает дополнительные рамки аватара, цвета ника и фоны карточки. «Полный газ» — все варианты оформления.</p>
      <div className="avatar-editor-subscription-actions">
        <a className="avatar-editor-boosty" href={subscription?.blog_url || 'https://boosty.to/turbotears'} target="_blank" rel="noopener noreferrer">Посмотреть подписки на Boosty ↗</a>
        <button type="button" className="avatar-editor-subscription-check" disabled={locked || subscriptionLoading || subscription?.can_check === false} onClick={() => void checkSubscription()}>{subscriptionBusy ? 'Проверяем подписку…' : 'Проверить подписку'}</button>
      </div>
      <div className="profile-customize">{(['frame', 'color', 'background'] as const).map(key => <fieldset key={key} disabled={locked}>
        <legend>{{ frame: 'Рамка аватара', color: 'Цвет ника', background: 'Фон карточки' }[key]}</legend>
        {Object.entries(styleOptions[key]).map(([value, requiredTier]) => <button type="button" key={value}
          disabled={requiredTier > tier} aria-pressed={styleDraft[key] === value}
          title={requiredTier > tier ? `Доступно с подпиской «${requiredTier === 3 ? 'Полный газ' : 'Свой стиль'}» на Boosty` : labels[value]}
          onClick={() => { setStyleDraft({ ...styleDraft, [key]: value }); setError(''); }}>
          {labels[value]}{requiredTier > tier && ' · 🔒'}
        </button>)}
      </fieldset>)}</div>
      <div className="avatar-editor-subscription-status">
        <p className="profile-muted" role="status" aria-live="polite">{subscriptionLoading ? 'Загружаем статус подписки…' : subscription ? boostySubscriptionLabel(subscription) : 'Статус подписки недоступен.'}</p>
        {subscription?.premium_override !== null && subscription?.premium_override !== undefined && <p className="profile-muted">{subscription.premium_override ? 'Премиум включён вручную.' : 'Премиум отключён вручную.'}</p>}
        {subscription?.check_unavailable_reason && <p className="profile-muted">{subscription.check_unavailable_reason} <Link to="/account">Открыть аккаунт →</Link></p>}
        {subscription?.checked_at && <p className="profile-muted">Последняя проверка: {new Date(subscription.checked_at * 1000).toLocaleString('ru-RU')}</p>}
        {subscription?.check_failed && <p className="profile-muted" role="alert">{boostyCheckFailureLabel(subscription)}</p>}
        {subscriptionError && <p className="avatar-editor-subscription-error" role="alert">{subscriptionError}</p>}
      </div>
    </section>
    <footer><p role={error ? 'alert' : undefined} className="avatar-editor-error">{error}</p><div>
      <button type="button" disabled={locked} onClick={close}>Отмена</button>
      <button type="button" className="avatar-editor-save" disabled={locked || !dirty} onClick={() => void save()}>{busy ? 'Сохраняем…' : 'Сохранить изменения'}</button>
    </div></footer>
  </dialog>;
}
