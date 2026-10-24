import { Link } from 'react-router-dom';
import { AccountShortcut } from './AccountShortcut';
import { ThemeToggle } from './ThemeToggle';
import { NotificationShortcut } from './NotificationShortcut';
import { MenuShortcut } from './MenuShortcut';

export function HomeToolbar() {
  return <div className="home-toolbar">
    <Link to="/" className="home-toolbar-brand" aria-label="TurboTears — главная"><span>Turbo</span><span>Tears</span></Link>
    <div className="home-toolbar-actions"><ThemeToggle /><NotificationShortcut /><AccountShortcut /><MenuShortcut /></div>
  </div>;
}
