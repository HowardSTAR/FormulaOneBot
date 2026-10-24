import { Link } from 'react-router-dom';
import { HomeIcon } from './HomeIcon';

export function HomeShortcuts() {
  return <nav className="home-explore" aria-label="Подробнее о чемпионате">
    <Link to="/race-results" data-analytics-action="results_open"><HomeIcon name="results" /><span>Результаты сессий</span><HomeIcon name="chevronRight" /></Link>
    <Link to="/wiki" data-analytics-action="wiki_open"><HomeIcon name="help" /><span>Как устроен чемпионат</span><HomeIcon name="chevronRight" /></Link>
  </nav>;
}
