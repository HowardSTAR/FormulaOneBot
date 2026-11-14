import './championship-backdrop.css';

export function ChampionshipBackdrop() {
  return <span className="championship-backdrop" aria-hidden="true">
    <svg viewBox="0 0 1000 120" focusable="false"><text x="500" y="96" textAnchor="middle" textLength="960" lengthAdjust="spacingAndGlyphs">WORLD CHAMPION</text></svg>
  </span>;
}
