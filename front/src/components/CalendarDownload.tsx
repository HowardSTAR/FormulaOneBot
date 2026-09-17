import { calendarText } from '../helpers/calendar';
export function CalendarDownload({title, start}: {title: string; start?: string}) {
  const text = start ? calendarText(title, start, window.location.href.split('#')[0]) : null;
  return text ? <a className="calendar-download" download="f1-session.ics" href={`data:text/calendar;charset=utf-8,${encodeURIComponent(text)}`} aria-label={`Добавить в календарь: ${title}`}>В календарь +</a> : null;
}
