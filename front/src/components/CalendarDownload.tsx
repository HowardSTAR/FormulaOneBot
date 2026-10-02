import { useEffect, useId, useRef, useState } from 'react';
import { apiAssetUrl } from '../helpers/api';
import { openExternalLink } from '../helpers/telegram';
export function CalendarDownload({title, start}: {title: string; start?: string}) {
  const [open, setOpen] = useState(false);
  const [requested, setRequested] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  useEffect(() => {
    if (open) dialog.current?.showModal(); else dialog.current?.close();
  }, [open]);
  if (!start || !Number.isFinite(Date.parse(start)) || !/(Z|[+-]\d\d:\d\d)$/i.test(start)) return null;
  const href = apiAssetUrl('/api/calendar/session.ics', {title, start});
  return <>
    <button type="button" className="calendar-download" aria-label={`Добавить в календарь: ${title}`} aria-haspopup="dialog" onClick={() => {setRequested(false); setOpen(true);}}>В календарь +</button>
    <dialog className="calendar-dialog" ref={dialog} aria-labelledby={heading} onCancel={() => setOpen(false)} onClose={() => setOpen(false)}>
      <h2 id={heading}>Добавить сессию</h2><p>{title}</p>
      <p>Скачайте файл и откройте его в Apple Calendar, Outlook или импортируйте в Google Календарь. Добавление нужно подтвердить в календаре.</p>
      <a className="ui-action-link" href={href} download="f1-session.ics" onClick={event => {
        if (openExternalLink(href)) event.preventDefault();
        setRequested(true);
      }}>Скачать событие .ics ↓</a>
      {requested && <p role="status">Если файл не открылся автоматически, найдите «f1-session.ics» в загрузках браузера и откройте его в календаре.</p>}
      <p className="calendar-note">Сохранено время старта. Если расписание изменится, событие в вашем календаре потребуется обновить.</p>
      <button type="button" onClick={() => setOpen(false)}>Закрыть</button>
    </dialog>
  </>;
}
