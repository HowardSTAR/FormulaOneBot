import { Link } from 'react-router-dom';
import { homeSectionPath } from '../helpers/homeSections';

export function GameExit({ playing = false }: { playing?: boolean }) {
  return <div className={`game-exit-row${playing ? ' is-playing' : ''}`}>
    <Link to={homeSectionPath('games')} className="game-exit-link">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10 4H4v16h6m4-13 5 5-5 5M9 12h10" /></svg>
      <span>Выйти из игры</span>
    </Link>
  </div>;
}
