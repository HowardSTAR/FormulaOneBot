export function calendarText(title: string, start: string, pageUrl: string): string | null {
  const date = new Date(start);
  if (!start || !Number.isFinite(date.getTime())) return null;
  const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const escape = (s: string) => s.replace(/\\/g, '\\\\').replace(/\r?\n/g, '\\n').replace(/;/g, '\\;').replace(/,/g, '\\,');
  // Fold by UTF-8 octets, not JS characters (Russian labels use multibyte UTF-8).
  const fold = (s: string) => {
    let line = '', result = '', bytes = 0;
    for (const ch of s) {
      const size = new TextEncoder().encode(ch).length;
      if (bytes + size > 74) {result += line + '\r\n'; line = ' '; bytes = 1;}
      line += ch; bytes += size;
    }
    return result + line;
  };
  return ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//TurboTears//Sessions//RU','CALSCALE:GREGORIAN',
    'BEGIN:VEVENT', `UID:${encodeURIComponent(title)}-${stamp(date)}@f1hub.ru`, `DTSTAMP:${stamp(new Date())}`,
    `DTSTART:${stamp(date)}`, `SUMMARY:${escape(title)}`, `URL:${pageUrl.replace(/[\r\n]/g, '')}`,
    'DESCRIPTION:Время начала сессии. Проверьте расписание перед этапом: оно может измениться.',
    'END:VEVENT','END:VCALENDAR'].map(fold).join('\r\n') + '\r\n';
}
