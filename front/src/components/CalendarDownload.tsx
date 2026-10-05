import { apiAssetUrl } from '../helpers/api';
import { openExternalLink } from '../helpers/telegram';

type Session = { utc_iso?: string };

export function CalendarDownload({title, season, round, sessions}: {
  title: string;
  season: number;
  round: number;
  sessions: Session[];
}) {
  const scheduled = sessions.filter(({utc_iso: start}) =>
    start && Number.isFinite(Date.parse(start)) && /(Z|[+-]\d\d:\d\d)$/i.test(start));
  if (!scheduled.length || !Number.isInteger(season) || season < 1950
    || !Number.isInteger(round) || round < 1) return null;
  const href = apiAssetUrl('/api/calendar/weekend.ics', {season, round});
  return <div className="calendar-weekend">
    <a className="calendar-download" href={href} download={`f1-weekend-${season}-${round}.ics`}
      aria-label={`Скачать все сессии в календарь: ${title}`}
      onClick={event => { if (openExternalLink(href)) event.preventDefault(); }}>
      Скачать весь этап ↓
    </a>
    <p className="calendar-note">Все сессии — одним файлом для календаря, от начала до ориентировочного окончания. Импорт нужно подтвердить в календаре.
      {scheduled.length < sessions.length && ' Сессии без времени старта появятся позже.'}
    </p>
  </div>;
}
