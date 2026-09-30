import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { pendingInvitation, rememberInvitation, sharingEvent, sharingTelegram, validShareToken } from '../helpers/sharing';

export function EngagementEntry() {
  const location = useLocation(), navigate = useNavigate(), auth = useAuthState();
  const startHandled = useRef(false);
  useEffect(() => {
    const start = sharingTelegram()?.initDataUnsafe?.start_param || new URLSearchParams(window.location.search).get('tgWebAppStartParam');
    const token = start?.startsWith('share_') ? start.slice(6) : '';
    if (!startHandled.current) {
      startHandled.current = true;
      if (token && validShareToken(token) && location.pathname === '/') navigate(`/share/${token}`, {replace: true});
    }
    const via = new URLSearchParams(location.search).get('via');
    if (via) rememberInvitation(via);
  }, [location.pathname, location.search, navigate]);
  useEffect(() => {
    const record = () => {const token = pendingInvitation(); if (auth.signedIn && token) void sharingEvent(token, 'arrival');};
    record();
    window.addEventListener(AUTH_CHANGED_EVENT, record);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, record);
  }, [auth.signedIn]);
  return null;
}
