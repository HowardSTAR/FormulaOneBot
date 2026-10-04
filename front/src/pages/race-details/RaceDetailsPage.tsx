import { Navigate, useLocation } from 'react-router-dom';

/** Preserve stage selection in saved links, bot messages and browser history. */
export default function RaceDetailsPage() {
  const location = useLocation();
  return <Navigate replace to={{pathname: '/next-race', search: location.search, hash: location.hash}} />;
}
