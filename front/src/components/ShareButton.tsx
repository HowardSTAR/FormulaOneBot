import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../helpers/api';
import { loadShareImage, sendCard, sharingEvent, type ShareCard, type ShareOptions } from '../helpers/sharing';
import './sharing.css';

export function ShareComposer({options, onClose}: {options: ShareOptions; onClose: () => void}) {
  return options.kind === 'race'
    ? <RaceShareComposer key={options.track_id} options={options} onClose={onClose} />
    : <CardShareComposer key={JSON.stringify(options)} options={options} onClose={onClose} />;
}

async function copyRaceLink(card: ShareCard): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(card.web_url);
    void sharingEvent(card.token, 'share_copied');
    return true;
  } catch { return false; }
}

function RaceShareComposer({options, onClose}: {options: ShareOptions; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const link = useRef<HTMLInputElement>(null);
  const request = useRef<Promise<ShareCard> | null>(null);
  const [card, setCard] = useState<ShareCard | null>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [copying, setCopying] = useState(false);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); previous?.focus(); };
  }, []);
  useEffect(() => {
    let active = true;
    // Reuse the pending creation during StrictMode's effect replay.
    request.current ??= apiRequest<ShareCard>('/api/engagement/shares', {...options, consent: true}, 'POST', 150000);
    void request.current.then(async created => {
      if (!active) return;
      setCard(created);
      const copied = await copyRaceLink(created);
      if (active) setStatus(copied ? 'Ссылка скопирована' : 'Нажмите «Скопировать» или скопируйте ссылку из поля.');
    }).catch(e => {
      if (active) setError(e instanceof Error ? e.message : 'Не удалось создать карточку');
    });
    return () => { active = false; };
  }, [options, attempt]);
  async function copy() {
    if (!card || copying) return;
    setCopying(true);
    const copied = await copyRaceLink(card);
    setStatus(copied ? 'Ссылка скопирована' : 'Выделите и скопируйте ссылку в поле.');
    if (!copied) { link.current?.focus(); link.current?.select(); }
    setCopying(false);
  }
  return <dialog ref={dialog} className="share-dialog race-share-dialog" aria-labelledby="race-share-heading" onCancel={event => {event.stopPropagation(); onClose();}}>
    <header><h2 id="race-share-heading">Поделиться заездом</h2><button type="button" onClick={onClose} aria-label="Закрыть ссылку">×</button></header>
    {card ? <>
      <p>Карточка создана. Друг сможет проехать эту трассу с вашим призраком. Ссылка действует 30 дней.</p>
      <div className="race-share-link-row">
        <input ref={link} type="url" aria-label="Ссылка на заезд" readOnly value={card.web_url} onFocus={e => e.target.select()} />
        <button type="button" className="share-primary" disabled={copying} onClick={() => void copy()}>Скопировать</button>
      </div>
    </> : !error && <p role="status">Готовим ссылку на заезд…</p>}
    {status && <p className="race-share-status" role="status">{status}</p>}
    {error && <><p role="alert">{error}</p><button type="button" onClick={() => { request.current = null; setError(''); setAttempt(value => value + 1); }}>Повторить</button></>}
  </dialog>;
}

function CardShareComposer({options, onClose}: {options: ShareOptions; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const link = useRef<HTMLInputElement>(null);
  const request = useRef<Promise<ShareCard> | null>(null);
  const [card, setCard] = useState<ShareCard | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [imageReady, setImageReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => {element?.close(); previous?.focus();};
  }, []);
  useEffect(() => {
    let active = true;
    // A click on Share creates the card; effect replay must not create a second one.
    request.current ??= apiRequest<ShareCard>('/api/engagement/shares', {...options, consent: true}, 'POST', 150000);
    void request.current.then(async created => {
      if (!active) return;
      setCard(created);
      const file = await loadShareImage(created);
      if (active) {setImage(file); setImageReady(true);}
    }).catch(e => {
      if (active) setError(e instanceof Error ? e.message : 'Не удалось подготовить карточку');
    });
    return () => { active = false; };
  }, [options, attempt]);
  async function send() {
    if (!card || busy || !imageReady) return;
    setBusy(true); setError('');
    try {
      const outcome = await sendCard(card, image);
      setStatus(outcome === 'sent' ? 'Карточка отправлена.' : outcome === 'cancelled' ? 'Отправка отменена.' : 'Открыто окно Telegram. Отправьте сообщение выбранному получателю.');
    } catch {setError('Не удалось отправить карточку. Попробуйте ещё раз или скачайте изображение ниже.');}
    finally {setBusy(false);}
  }
  async function copy() {
    if (!card) return;
    try {await navigator.clipboard.writeText(card.web_url); void sharingEvent(card.token, 'share_copied'); setStatus('Ссылка скопирована.');}
    catch {setStatus('Выделите и скопируйте ссылку в поле ниже.'); link.current?.focus(); link.current?.select();}
  }
  return <dialog ref={dialog} className="share-dialog" aria-labelledby="share-heading" onCancel={event => {event.stopPropagation(); onClose();}}>
    <header><h2 id="share-heading">Поделиться с друзьями</h2><button type="button" autoFocus onClick={onClose} aria-label="Закрыть отправку">×</button></header>
    {!card && !error && <div className="share-preparing" role="status"><span className="share-spinner" aria-hidden="true" /><strong>Создаём и сохраняем карточку…</strong><p>Она появится здесь, как только будет готова.</p></div>}
    {card && <>
      <p className="share-ready" role="status"><span aria-hidden="true">✓</span> Карточка сохранена</p>
      <p className="share-description">{options.kind === 'prediction' ? 'Ваше имя, очки и угаданные категории. Ответы прогноза скрыты.' : options.kind === 'league' ? 'Приглашение в лигу. Друг подтвердит вступление сам; ответы прогнозов скрыты.' : 'Карточка с проверенными фактами и ссылкой на этот раздел.'}</p>
      <img className="share-preview" src={card.image_url} alt={`${card.title}: ${card.headline}`} />
      {card.provisional && <p className="share-warning">Предварительный результат. Карточка отражает данные на момент создания.</p>}
      <div className="share-actions"><button className="share-primary" disabled={busy || !imageReady} onClick={() => void send()}>{busy ? 'Открываем отправку…' : !imageReady ? 'Готовим изображение…' : 'Отправить в Telegram'}</button><button onClick={() => void copy()}>Копировать ссылку</button><a href={card.image_url} download="f1hub-card.jpg">Скачать карточку</a></div>
      <label className="share-link-label">Ссылка для друзей<input ref={link} type="url" readOnly value={card.web_url} onFocus={e => e.target.select()} /></label>
      <small className="share-footnote">Ссылка действует 30 дней. Карточки можно отозвать в разделе «С друзьями».</small>
    </>}
    {status && <p className="share-feedback" role="status">{status}</p>}{error && <div className="share-error" role="alert"><p>{error}</p>{!card && <button type="button" onClick={() => {request.current = null; setError(''); setAttempt(v => v + 1);}}>Повторить создание</button>}</div>}
  </dialog>;
}

export function ShareButton({options, children = 'Поделиться результатом'}: {options: ShareOptions; children?: React.ReactNode}) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className="share-button" onClick={() => setOpen(true)}>{children}</button>{open && <ShareComposer options={options} onClose={() => setOpen(false)} />}</>;
}
