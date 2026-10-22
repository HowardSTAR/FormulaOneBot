import { Link } from 'react-router-dom';
import { HomeIcon, type HomeIconName } from './HomeIcon';

type HomeLink = { to: string; label: string; icon: HomeIconName };

export function HomeLinkList({ label, items }: { label: string; items: HomeLink[] }) {
  return <nav aria-label={label}><ul className="home-link-list">{items.map(item => <li key={item.to}>
    <Link to={item.to}><HomeIcon name={item.icon} /><span>{item.label}</span><HomeIcon name="chevronRight" /></Link>
  </li>)}</ul></nav>;
}
