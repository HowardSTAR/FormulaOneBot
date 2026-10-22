import { Link } from 'react-router-dom';
import { AccountShortcut } from './AccountShortcut';
import { ThemeToggle } from './ThemeToggle';

export function HomeToolbar() {
  return <div className="home-toolbar">
    <Link to="/" className="home-toolbar-brand" aria-label="TurboTears — главная"><span>Turbo</span><span>Tears</span></Link>
    <div className="home-toolbar-actions"><ThemeToggle /><AccountShortcut /></div>
  </div>;
}
