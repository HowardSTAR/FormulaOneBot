const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

export function SettingsSoundIcon({ quiet }: { quiet: boolean }) {
  return <svg className="settings-symbol" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {quiet ? <path d="M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14Z" /> : <><path d="m11 4-6 5H2v6h3l6 5V4Z" /><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" /></>}
  </svg>;
}

/** A 24-hour sound schedule, with the marker in the selected timezone. */
export function SettingsDayClock({ time, minutes, loaded, sound, quiet, draft }: {
  time: string; minutes: number | null; loaded: boolean; sound: boolean; quiet: boolean; draft: boolean;
}) {
  return <div className="settings-day-preview" aria-busy={!loaded}>
    <div className="settings-clock">
      <svg className="settings-clock-dial" viewBox="0 0 256 256" width="256" height="256" aria-hidden="true">
        <circle className="settings-clock-face" cx="128" cy="128" r="72" />
        {HOURS.map(hour => <line key={hour} className={`settings-clock-tick${hour % 6 === 0 ? ' is-major' : ''}`} x1="128" y1="24" x2="128" y2={hour % 6 === 0 ? 32 : 28} transform={`rotate(${hour * 15} 128 128)`} />)}
        <circle className="settings-clock-track" cx="128" cy="128" r="88" />
        {loaded && sound && <circle className="settings-clock-sound" cx="128" cy="128" r="88" pathLength="24" strokeDasharray="11 13" strokeDashoffset="-10" transform="rotate(-90 128 128)" />}
        {loaded && minutes !== null && <g transform={`rotate(${minutes / 4} 128 128)`}><circle className="settings-clock-marker" cx="128" cy="40" r="6" /></g>}
        <g className="settings-clock-numerals"><text x="128" y="14">00</text><text x="246" y="132">06</text><text x="128" y="250">12</text><text x="10" y="132">18</text></g>
      </svg>
      <div className="settings-clock-center"><span>Сейчас</span><strong>{loaded ? time : '—:—'}</strong><span>в вашем поясе</span></div>
    </div>
    <p className={`settings-sound-state${loaded && !quiet ? ' has-sound' : ''}`}><SettingsSoundIcon quiet={!loaded || quiet} /><span>{!loaded ? 'Загружаем режим…' : `${draft ? 'Будет' : 'Сейчас'} ${quiet ? 'без звука' : 'со звуком'}`}</span></p>
    <div className="settings-sound-schedule">
      <div><span className={`settings-schedule-dot${loaded && sound ? ' has-sound' : ''}`} aria-hidden="true" /><span>Со звуком</span><strong>{!loaded ? '—' : sound ? '10:00–21:00' : 'Выключен'}</strong></div>
      <div><SettingsSoundIcon quiet /><span>Тихие часы</span><strong>21:00–10:00</strong></div>
    </div>
  </div>;
}
