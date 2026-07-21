export type ReactionDesktopStatus =
  | "idle"
  | "starting"
  | "armed"
  | "running"
  | "finished"
  | "false-start";

type ReactionDesktopSceneProps = {
  status: ReactionDesktopStatus;
  activeLights: number;
  totalLights: number;
  currentTimeMs: number;
  resultTimeMs: number | null;
  bestTimeMs: number | null;
  onAction: () => void;
};

function DesktopF1Car() {
  return (
    <svg className="reaction-desktop-car" viewBox="0 0 420 640" role="img" aria-label="Болид Formula 1">
      <defs>
        <linearGradient id="carBody" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#d6d9de" />
          <stop offset="0.28" stopColor="#777d86" />
          <stop offset="0.62" stopColor="#292d33" />
          <stop offset="1" stopColor="#0c0f13" />
        </linearGradient>
        <linearGradient id="carWing" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#727780" />
          <stop offset="1" stopColor="#171a1f" />
        </linearGradient>
        <radialGradient id="carCockpit" cx="48%" cy="36%" r="64%">
          <stop offset="0" stopColor="#53606c" />
          <stop offset="0.45" stopColor="#171c22" />
          <stop offset="1" stopColor="#030506" />
        </radialGradient>
        <filter id="carShadow" x="-40%" y="-30%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="16" />
        </filter>
      </defs>

      <ellipse cx="210" cy="340" rx="112" ry="252" fill="#000" opacity="0.54" filter="url(#carShadow)" />

      <g className="reaction-car-wheels">
        <rect x="52" y="151" width="72" height="124" rx="24" />
        <rect x="296" y="151" width="72" height="124" rx="24" />
        <rect x="44" y="412" width="82" height="142" rx="27" />
        <rect x="294" y="412" width="82" height="142" rx="27" />
        <path d="M61 166h54M61 257h54M305 166h54M305 257h54M54 430h62M54 535h62M304 430h62M304 535h62" />
      </g>

      <path className="reaction-car-rear-wing" d="M93 544h234l22 50H71z" fill="url(#carWing)" />
      <rect x="108" y="568" width="204" height="27" rx="7" fill="#111419" stroke="#8c929a" strokeWidth="3" />
      <path className="reaction-car-front-wing" d="M78 93h264l31 46H47z" fill="url(#carWing)" />
      <rect x="65" y="106" width="290" height="23" rx="7" fill="#16191e" stroke="#a3a8af" strokeWidth="3" />

      <path
        d="M210 64c29 0 43 22 46 58l9 102 53 60-34 65-15 150-59 80-59-80-15-150-34-65 53-60 9-102c3-36 17-58 46-58z"
        fill="url(#carBody)"
        stroke="#c7cbd1"
        strokeWidth="4"
      />
      <path d="M155 225l-62 68 48 32 41-54zM265 225l62 68-48 32-41-54z" fill="#30353c" stroke="#8b9199" strokeWidth="3" />
      <path d="M151 344l-43 75 42 69 31-83zM269 344l43 75-42 69-31-83z" fill="#20242a" stroke="#686e77" strokeWidth="3" />
      <path d="M210 82v474" fill="none" stroke="#f0f2f5" strokeOpacity="0.36" strokeWidth="3" />
      <path d="M176 265c4-46 16-73 34-73s30 27 34 73l-9 82h-50z" fill="url(#carCockpit)" stroke="#9ea4ac" strokeWidth="4" />
      <ellipse cx="210" cy="274" rx="25" ry="38" fill="#050709" stroke="#9ca3ac" strokeWidth="4" />
      <path d="M178 251c18-18 46-18 64 0M180 251v62M240 251v62" fill="none" stroke="#c5c9cf" strokeWidth="7" strokeLinecap="round" />
      <path d="M171 446l39 91 39-91-14-71h-50z" fill="#14181d" opacity="0.9" />
      <circle cx="210" cy="156" r="11" fill="#e10600" />
    </svg>
  );
}

function getStatusCopy(status: ReactionDesktopStatus, activeLights: number, totalLights: number) {
  if (status === "starting") return `ОГНИ ${activeLights}/${totalLights}`;
  if (status === "armed") return "ЖДИТЕ СИГНАЛ";
  if (status === "running") return "СТАРТ!";
  if (status === "finished") return "РЕЗУЛЬТАТ";
  if (status === "false-start") return "ФАЛЬСТАРТ";
  return "ГОТОВ К СТАРТУ";
}

function getActionLabel(status: ReactionDesktopStatus) {
  if (status === "false-start") return "ПОПРОБОВАТЬ СНОВА";
  if (status === "finished") return "СЫГРАТЬ ЕЩЕ РАЗ";
  if (status === "starting" || status === "armed") return "ЖДИТЕ";
  if (status === "running") return "ФИНИШ";
  return "СТАРТ";
}

export function ReactionDesktopScene({
  status,
  activeLights,
  totalLights,
  currentTimeMs,
  resultTimeMs,
  bestTimeMs,
  onAction,
}: ReactionDesktopSceneProps) {
  const resultText =
    status === "false-start"
      ? "Фальстарт! Вы нажали слишком рано"
      : status === "finished" && resultTimeMs != null
        ? `Ваше время: ${Math.round(resultTimeMs)} мс`
        : status === "running"
          ? `${Math.round(currentTimeMs)} мс`
          : status === "starting" || status === "armed"
            ? "Не нажимайте до погасания огней"
            : "Сконцентрируйтесь на стартовых огнях";

  return (
    <section className={`reaction-desktop-stage is-${status}`} data-game-state={status} aria-live="polite">
      <div className="reaction-desktop-grid" aria-hidden="true" />
      <div className="reaction-desktop-status">{getStatusCopy(status, activeLights, totalLights)}</div>

      <div className="reaction-desktop-lights" aria-label={`${activeLights} из ${totalLights} стартовых огней горят`}>
        {Array.from({ length: totalLights }).map((_, index) => (
          <div key={index} className={`reaction-desktop-light ${index < activeLights ? "is-lit" : ""}`}>
            <span />
          </div>
        ))}
      </div>

      <div className="reaction-desktop-car-zone">
        <div className="reaction-grid-slot reaction-grid-slot-left" aria-hidden="true" />
        <DesktopF1Car />
        <div className="reaction-grid-slot reaction-grid-slot-right" aria-hidden="true" />
      </div>

      <div className={`reaction-desktop-result ${status === "false-start" ? "is-error" : ""}`}>
        <strong>{resultText}</strong>
        {bestTimeMs != null && <span>Лучшее время: {Math.round(bestTimeMs)} мс</span>}
      </div>

      <div className="reaction-desktop-controls">
        <button type="button" className="reaction-desktop-start" onClick={onAction}>
          {getActionLabel(status)}
        </button>
        <div className="reaction-desktop-hint">
          Нажмите кнопку или клавишу <kbd>Пробел</kbd> <span>(Space)</span>
        </div>
      </div>
    </section>
  );
}
