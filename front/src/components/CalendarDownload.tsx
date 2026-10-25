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
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 2v4m8-4v4M3 10h18M12 13v6m-3-3 3 3 3-3" /><rect x="3" y="4" width="18" height="18" rx="3" /></svg>
      Скачать весь этап
    </a>
    <details className="calendar-help"><summary>Как добавить?</summary><p className="calendar-note">Все сессии — одним файлом для календаря, от начала до ориентировочного окончания. Импорт нужно подтвердить в календаре.
      {scheduled.length < sessions.length && ' Сессии без времени старта появятся позже.'}
    </p></details>
  </div>;
}
