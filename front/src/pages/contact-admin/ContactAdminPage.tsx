import { FormEvent, useState } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import "./contact-admin.css";

export default function ContactAdminPage() {
  const [senderName, setSenderName] = useState("");
  const [senderContact, setSenderContact] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSending(true);
    setError("");
    setSent(false);
    try {
      await apiRequest(
        "/api/contact-admin",
        { sender_name: senderName, sender_contact: senderContact, message },
        "POST",
      );
      setSent(true);
      setMessage("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось отправить сообщение");
    } finally {
      setSending(false);
    }
  };

  return (
    <main className="contact-admin-page">
      <BackButton>← <span>Назад</span></BackButton>
      <div className="contact-admin-layout">
        <section className="contact-admin-intro">
          <span>Direct line</span>
          <h2>Связаться<br />с админом</h2>
          <p>Сообщение уйдёт напрямую администратору F1Hub в Telegram.</p>
          <div className="contact-admin-route" aria-hidden>
            <i>01</i><b /><i>02</i><b /><i>03</i>
          </div>
        </section>

        <form className="contact-admin-form" onSubmit={(event) => void submit(event)}>
          <label>
            <span>Имя</span>
            <input value={senderName} onChange={(event) => setSenderName(event.target.value)} maxLength={80} placeholder="Как к вам обращаться" required />
          </label>
          <label>
            <span>Контакт</span>
            <input value={senderContact} onChange={(event) => setSenderContact(event.target.value)} maxLength={120} placeholder="@username, email или телефон" required />
          </label>
          <label>
            <span>Сообщение</span>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} maxLength={3000} rows={8} placeholder="Опишите вопрос или предложение" required />
          </label>
          <div className="contact-admin-counter">{message.length}/3000</div>
          {error && <div className="contact-admin-status is-error">{error}</div>}
          {sent && <div className="contact-admin-status is-success">Сообщение доставлено администратору.</div>}
          <button disabled={sending || senderName.trim().length < 2 || senderContact.trim().length < 2 || message.trim().length < 5}>
            {sending ? "Отправляем…" : "Отправить в Telegram"}
          </button>
        </form>
      </div>
    </main>
  );
}
