import { Link } from 'react-router-dom';
import { AccountShortcut } from './AccountShortcut';
import { ThemeToggle } from './ThemeToggle';
import { NotificationShortcut } from './NotificationShortcut';

export function HomeToolbar({ desktop }: { desktop: boolean }) {
  return <div className="home-toolbar">
    <Link to="/" className="home-toolbar-brand" aria-label="TurboTears — главная"><span>Turbo</span><span>Tears</span></Link>
    <div className="home-toolbar-actions"><ThemeToggle /><NotificationShortcut showReminder={desktop} /><AccountShortcut /></div>
  </div>;
}
