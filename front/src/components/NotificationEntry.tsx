import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { trackNotificationEntry } from '../helpers/notificationEntry';

export function NotificationEntry() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const token = params.get('nb');
    if (!token) return;
    let active = true;
    void trackNotificationEntry(token, location.pathname, location.key).then(recorded => {
      if (recorded && active) {
        params.delete('nb');
        navigate({pathname:location.pathname, search:params.toString(), hash:location.hash}, {replace:true});
      }
    });
    return () => {active = false;};
  }, [location.pathname, location.search, location.hash, location.key, navigate]);
  return null;
}
