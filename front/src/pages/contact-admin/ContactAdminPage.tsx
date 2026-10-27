import { type FormEvent, useRef, useState } from 'react';
import { BackButton } from '../../components/BackButton';
import { HomeIcon } from '../index/HomeIcon';
import { apiRequest } from '../../helpers/api';
import '../index/home-sections.css';
import './contact-admin.css';

export default function ContactAdminPage() {
  const [senderName, setSenderName] = useState('');
  const [senderContact, setSenderContact] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [sent, setSent] = useState(false);
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const pending = useRef(false);
  const status = useRef<HTMLDivElement>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending.current) return;
    const errors: Record<string, string> = {};
    if (senderName.trim().length < 2) errors.sender_name = 'Введите имя: не меньше 2 символов.';
    if (senderContact.trim().length < 2) errors.sender_contact = 'Оставьте контакт, по которому можно ответить.';
    if (message.trim().length < 5) errors.message = 'Опишите обращение: не меньше 5 символов.';
    setInvalid(errors);
    setSent(false);
    setError('');
    const first = Object.keys(errors)[0];
    if (first) {
      event.currentTarget.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
      return;
    }
    pending.current = true;
    setSending(true);
    try {
      await apiRequest('/api/contact-admin', {
        sender_name: senderName.trim(), sender_contact: senderContact.trim(), message: message.trim(),
      }, 'POST');
      setSent(true);
      setMessage('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось отправить сообщение. Попробуйте ещё раз.');
    } finally {
      pending.current = false;
      setSending(false);
      requestAnimationFrame(() => status.current?.focus());
    }
  };

  const edit = (name: string) => {
    setInvalid(current => { const next = { ...current }; delete next[name]; return next; });
    setSent(false);
  };

  return <main className="contact-admin-page">
    <BackButton>← <span>Назад</span></BackButton>
    <div className="contact-admin-layout">
      <header className="contact-admin-intro">
        <h1>Обратная связь</h1>
        <p className="contact-admin-lead">Что улучшим в TurboTears?</p>
        <p>Расскажите об ошибке, предложите идею или задайте вопрос. Сообщение придёт администратору в Telegram.</p>
        <div className="contact-admin-art home-feedback-art" aria-hidden="true"><span className="home-feedback-note"><i /><i /><i /></span><HomeIcon name="contact" /><span className="home-feedback-reply"><i /><i /><i /></span></div>
        <div className="contact-admin-hints">
          <h2>Помогите разобраться</h2>
          <p>Если нашли ошибку, укажите страницу, что вы сделали и что произошло. Для вопроса о данных или авторских правах опишите, чего касается запрос.</p>
        </div>
      </header>
      <form className="contact-admin-form" onSubmit={event => void submit(event)} noValidate aria-label="Сообщение администратору" aria-busy={sending}>
        <div className="contact-admin-field-row">
          <div className="contact-admin-field"><label htmlFor="contact-name">Имя</label>
            <input id="contact-name" name="sender_name" autoComplete="name" value={senderName} onChange={event => { setSenderName(event.target.value); edit('sender_name'); }} maxLength={80} placeholder="Как к вам обращаться…" required disabled={sending} aria-invalid={Boolean(invalid.sender_name)} aria-describedby={invalid.sender_name ? 'contact-name-error' : undefined} />
            {invalid.sender_name && <small id="contact-name-error" className="contact-admin-field-error">{invalid.sender_name}</small>}
          </div>
          <div className="contact-admin-field"><label htmlFor="contact-reply">Контакт</label>
            <input id="contact-reply" name="sender_contact" autoComplete="off" spellCheck={false} value={senderContact} onChange={event => { setSenderContact(event.target.value); edit('sender_contact'); }} maxLength={120} placeholder="@username, email или телефон…" required disabled={sending} aria-invalid={Boolean(invalid.sender_contact)} aria-describedby={`contact-reply-hint${invalid.sender_contact ? ' contact-reply-error' : ''}`} />
            <small id="contact-reply-hint">Чтобы вам могли ответить.</small>
            {invalid.sender_contact && <small id="contact-reply-error" className="contact-admin-field-error">{invalid.sender_contact}</small>}
          </div>
        </div>
        <div className="contact-admin-field"><label htmlFor="contact-message">Сообщение</label>
          <textarea id="contact-message" name="message" autoComplete="off" value={message} onChange={event => { setMessage(event.target.value); edit('message'); }} maxLength={3000} rows={7} placeholder="Ваш вопрос или предложение…" required disabled={sending} aria-invalid={Boolean(invalid.message)} aria-describedby={`contact-message-hint${invalid.message ? ' contact-message-error' : ''}`} />
          {invalid.message && <small id="contact-message-error" className="contact-admin-field-error">{invalid.message}</small>}
        </div>
        <div className="contact-admin-message-meta"><small id="contact-message-hint">Не отправляйте пароли и коды входа.</small><span className="contact-admin-counter" aria-label={`${message.length} из 3000 символов`}>{message.length} / 3000</span></div>
        {(error || sent) && <div ref={status} tabIndex={-1} className={`contact-admin-status ${error ? 'is-error' : 'is-success'}`} role={error ? 'alert' : 'status'}>
          <strong>{error ? 'Сообщение не отправлено' : 'Сообщение доставлено администратору.'}</strong>
          <p>{error ? `${error} Текст сохранён в форме — попробуйте отправить ещё раз.` : 'Контакт для ответа передан вместе с сообщением.'}</p>
        </div>}
        <button type="submit" disabled={sending}><HomeIcon name="contact" />{sending ? 'Отправляем…' : 'Отправить в Telegram'}</button>
      </form>
    </div>
  </main>;
}
