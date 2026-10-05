import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';

type Audience = {telegram:number; web:number};
type Preview = {
  season:number; round:number; event_name:string; fingerprint:string; body:string;
  provisional:boolean; participants:number; recipients:Audience; already_sent:boolean;
};
type Receipt = {recipients:Audience; already_sent:boolean};
const endpoint = '/api/admin/tools/prediction-results';

export function PredictionResultBroadcast({season, round, disabled, onBusy}: {
  season:number; round:number; disabled:boolean; onBusy:(busy:boolean)=>void;
}) {
  const [preview, setPreview] = useState<Preview|null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState<Receipt|null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true); setPreview(null); setConfirmation(''); setError(''); setReceipt(null);
    apiRequest<Preview>(`${endpoint}/preview`, {season, round}).then(data => {
      if (active) setPreview(data);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : String(reason));
    }).finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [season, round, revision]);

  const send = async () => {
    if (!preview || confirmation !== 'ОТПРАВИТЬ' || sending || disabled) return;
    setSending(true); onBusy(true); setError('');
    try {
      const result = await apiRequest<Receipt>(`${endpoint}/send`, {
        season, round, fingerprint:preview.fingerprint, confirmation,
      }, 'POST');
      setReceipt(result); setPreview({...preview, already_sent:true, recipients:result.recipients});
      setConfirmation('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {setSending(false); onBusy(false);}
  };

  return <section className="prediction-broadcast" aria-label="Рассылка итогов прогнозов">
    <h3>Рассылка итогов · {season}, этап {round}</h3>
    <p>Отправьте сохранённые результаты этапа в Telegram и уведомления сайта. Пересчёт для отправки не требуется.</p>
    <button disabled={disabled || sending || loading} onClick={() => setRevision(value => value + 1)}>Обновить предпросмотр рассылки</button>
    {loading && <p role="status">Загружаем итоги и получателей…</p>}
    {error && <p role="alert" className="admin-notice error">{error}</p>}
    {preview && <>
      <p><strong>{preview.event_name}</strong> · рассчитано прогнозов: {preview.participants}.</p>
      {preview.provisional && <p>Часть фактов ещё не подтверждена. Сообщение будет отправлено как предварительные итоги.</p>}
      <pre className="prediction-broadcast-preview">{preview.body}</pre>
      <p>Получатели: Telegram — {preview.recipients.telegram}, веб — {preview.recipients.web}.</p>
      {preview.already_sent && !receipt && <p role="status">Эти итоги уже отправлены вручную. Повторная рассылка тех же результатов не создаётся.</p>}
      {!preview.already_sent && <fieldset disabled={disabled || sending}>
        <label>Для отправки в Telegram и веб введите ОТПРАВИТЬ
          <input value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="off"/>
        </label>
        <button disabled={confirmation !== 'ОТПРАВИТЬ' || !preview.recipients.telegram && !preview.recipients.web}
                onClick={() => void send()}>{sending ? 'Создаём рассылку…' : 'Разослать итоги в Telegram и веб'}</button>
      </fieldset>}
      <small>Telegram доставляет работающий бот. В вебе сообщение появится в «Уведомлениях», а push получат подписанные устройства. После изменения результатов можно отправить новые итоги.</small>
    </>}
    {receipt && <p role="status" className="admin-notice success">
      {receipt.already_sent ? 'Эти итоги уже отправлены.' : 'Рассылка создана.'} Telegram: {receipt.recipients.telegram} получателей в очереди; веб: {receipt.recipients.web} уведомлений. Дубли не созданы.
    </p>}
  </section>;
}
