import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { apiRequest } from '../helpers/api';
import { AUTH_CHANGED_EVENT, useAuthState } from '../helpers/auth';
import { TROPHY_CHECK, TROPHY_UPDATED, mergeTrophyQueue, type TrophyAward, type TrophyCollection } from '../helpers/trophies';

const Celebration = lazy(() => import('./TrophyCelebration'));

/** Listen to accepted results, not clicks or locally calculated game scores. */
export default function TrophyUnlock() {
  const auth = useAuthState();
  const [queue, setQueue] = useState<TrophyAward[]>([]);
  const [blocked, setBlocked] = useState(false);
  const dismissed = useRef(new Set<string>());
  const identityEpoch = useRef(Symbol());
  useEffect(() => {
    if (!auth.signedIn) return;
    let active = true, version = 0, subject: number | null = null;
    const refresh = () => {
      const requestVersion = ++version;
      void apiRequest<TrophyCollection>('/api/profiles/me/trophies').then(data => {
        if (!active || requestVersion !== version || !Array.isArray(data.pending)) return;
        if (subject !== data.user_id) { dismissed.current.clear(); subject = data.user_id; }
        setQueue(mergeTrophyQueue(data.pending, dismissed.current));
        window.dispatchEvent(new CustomEvent(TROPHY_UPDATED, { detail: data }));
      }).catch(() => { /* Awards stay pending on the server for the next successful check. */ });
    };
    const identityChanged = () => { identityEpoch.current=Symbol(); version++; subject = null; dismissed.current.clear(); setQueue([]); refresh(); };
    const visible = () => { if (document.visibilityState === 'visible') refresh(); };
    refresh();
    window.addEventListener(TROPHY_CHECK, refresh);
    window.addEventListener(AUTH_CHANGED_EVENT, identityChanged);
    document.addEventListener('visibilitychange', visible);
    return () => {
      active = false;
      identityEpoch.current=Symbol();
      window.removeEventListener(TROPHY_CHECK, refresh);
      window.removeEventListener(AUTH_CHANGED_EVENT, identityChanged);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [auth.signedIn]);
  useEffect(() => {
    const check = () => setBlocked(Boolean(document.documentElement.dataset.onboardingActive
      || document.documentElement.dataset.profileGuideActive || document.querySelector('dialog[open]:not(.trophy-unlock)')));
    const observer = new MutationObserver(check);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-onboarding-active','data-profile-guide-active'] });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['open'] });
    check();
    return () => observer.disconnect();
  }, []);
  async function acknowledge(all: boolean) {
    const epoch = identityEpoch.current;
    const ids = (all ? queue.slice(0,60) : queue.slice(0,1)).map(award => award.id);
    await apiRequest('/api/profiles/me/trophies/seen', { ids }, 'POST');
    if (epoch !== identityEpoch.current) return;
    ids.forEach(id => dismissed.current.add(id));
    setQueue(previous => previous.filter(award => !ids.includes(award.id)));
  }
  return auth.signedIn && !blocked && queue.length > 0
    ? <Suspense fallback={null}><Celebration key={queue[0].id} award={queue[0]} remaining={queue.length} onAcknowledge={acknowledge} /></Suspense> : null;
}
