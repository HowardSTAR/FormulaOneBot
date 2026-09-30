import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../helpers/api';
import { sendCard, sharingEvent, type ShareCard, type ShareOptions } from '../helpers/sharing';
import './sharing.css';

export function ShareComposer({options, onClose}: {options: ShareOptions; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [card, setCard] = useState<ShareCard | null>(null);
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
    try {setCard(await apiRequest<ShareCard>('/api/engagement/shares', {...options, consent: true}, 'POST', 150000));}
    catch (e) {setError(e instanceof Error ? e.message : 'Не удалось подготовить карточку');}
    finally {setBusy(false);}
  }
  async function send() {
    if (!card || busy) return;
    setBusy(true); setError('');
    try {
      const outcome = await sendCard(card);
      setStatus(outcome === 'sent' ? 'Карточка отправлена.' : outcome === 'cancelled' ? 'Отправка отменена.' : 'Открыто окно Telegram. Отправьте сообщение выбранному получателю.');
    } catch {setError('Не удалось открыть отправку. Скопируйте ссылку ниже.');}
    finally {setBusy(false);}
  }
  async function copy() {
    if (!card) return;
    try {await navigator.clipboard.writeText(card.share_url); void sharingEvent(card.token, 'share_copied'); setStatus('Ссылка скопирована.');}
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
      <input aria-label="Ссылка для друзей" readOnly value={card.share_url} onFocus={e => e.target.select()} />
    </>}
    {status && <p role="status">{status}</p>}{error && <p role="alert">{error}</p>}
  </dialog>;
}

export function ShareButton({options, children = 'Поделиться результатом'}: {options: ShareOptions; children?: React.ReactNode}) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className="share-button" onClick={() => setOpen(true)}>{children}</button>{open && <ShareComposer options={options} onClose={() => setOpen(false)} />}</>;
}
