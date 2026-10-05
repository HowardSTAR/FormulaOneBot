import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../helpers/api';
import { loadShareImage, sendCard, sharingEvent, type ShareCard, type ShareOptions } from '../helpers/sharing';
import './sharing.css';

export function ShareComposer({options, onClose}: {options: ShareOptions; onClose: () => void}) {
  return options.kind === 'race'
    ? <RaceShareComposer key={options.track_id} options={options} onClose={onClose} />
    : <ConfirmedShareComposer options={options} onClose={onClose} />;
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
  return <dialog ref={dialog} className="share-dialog race-share-dialog" aria-labelledby="race-share-heading" onCancel={onClose}>
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

function ConfirmedShareComposer({options, onClose}: {options: ShareOptions; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [card, setCard] = useState<ShareCard | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [consent, setConsent] = useState(false);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => {element?.close(); previous?.focus();};
  }, []);
  async function create() {
    if (!consent || busy) return;
    setBusy(true); setError('');
    try {
      const created = await apiRequest<ShareCard>('/api/engagement/shares', {...options, consent: true}, 'POST', 150000);
      setImage(await loadShareImage(created));
      setCard(created);
    }
    catch (e) {setError(e instanceof Error ? e.message : 'Не удалось подготовить карточку');}
    finally {setBusy(false);}
  }
  async function send() {
    if (!card || busy) return;
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
    catch {setStatus('Выделите и скопируйте ссылку в поле ниже.');}
  }
  return <dialog ref={dialog} className="share-dialog" aria-labelledby="share-heading" onCancel={onClose}>
    <header><h2 id="share-heading">Поделиться с друзьями</h2><button type="button" onClick={onClose} aria-label="Закрыть отправку">×</button></header>
    {!card ? <>
      <p>{options.kind === 'prediction' ? 'На карточке будут ваше имя участника, очки и угаданные категории. Сами ответы прогноза не публикуются.' : options.kind === 'race' ? 'На карточке будут ваше игровое имя и лучший сохранённый заезд на этой трассе. Друг сможет повторить его с вашим призраком.' : options.kind === 'league' ? 'Любой получивший приглашение сможет вступить в лигу после отдельного подтверждения. Ответы прогнозов не раскрываются.' : 'Подготовим карточку с проверенными фактами и переходом в этот раздел.'}</p>
      <label className="share-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />Разрешаю создать публичную ссылку на карточку на 30 дней.</label>
      <small>Сообщения не отправляются автоматически. Карточки, созданные после входа, можно отозвать в разделе «С друзьями»; уже пересланные изображения останутся у получателей.</small>
      <button className="share-primary" disabled={!consent || busy} onClick={() => void create()}>{busy ? 'Готовим карточку…' : 'Создать карточку'}</button>
    </> : <>
      <img className="share-preview" src={card.image_url} alt={`${card.title}: ${card.headline}`} />
      {card.provisional && <p className="share-warning">Предварительный результат. Карточка отражает данные на момент создания.</p>}
      <div className="share-actions"><button className="share-primary" disabled={busy} onClick={() => void send()}>{busy ? 'Открываем отправку…' : 'Отправить в Telegram'}</button><button onClick={() => void copy()}>Копировать ссылку</button><a href={card.image_url} download="f1hub-card.jpg">Скачать карточку</a></div>
      <input aria-label="Ссылка для друзей" readOnly value={card.web_url} onFocus={e => e.target.select()} />
    </>}
    {status && <p role="status">{status}</p>}{error && <p role="alert">{error}</p>}
  </dialog>;
}

export function ShareButton({options, children = 'Поделиться результатом'}: {options: ShareOptions; children?: React.ReactNode}) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className="share-button" onClick={() => setOpen(true)}>{children}</button>{open && <ShareComposer options={options} onClose={() => setOpen(false)} />}</>;
}
