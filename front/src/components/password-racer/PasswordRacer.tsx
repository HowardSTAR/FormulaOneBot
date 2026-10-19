import { useEffect, useRef, useState } from 'react';
import type { PasswordStrengthLevel } from '../../helpers/passwordRacerState';
import './password-racer.css';

export type PasswordRacerProps = {
  passwordStrengthLevel: PasswordStrengthLevel;
  isPasswordVisible: boolean;
  quality?: 'auto' | 'low' | 'high';
};

/** Privacy boundary: the scene receives two UI states, never the password. */
export default function PasswordRacer({ passwordStrengthLevel, isPasswordVisible, quality = 'auto' }: PasswordRacerProps) {
  const host = useRef<HTMLDivElement>(null);
  const control = useRef<Awaited<ReturnType<typeof import('./createPasswordRacer')['createPasswordRacer']>> | null>(null);
  const latest = useRef({ passwordStrengthLevel, isPasswordVisible });
  const [status, setStatus] = useState<'loading' | 'ready' | 'fallback'>('loading');

  useEffect(() => {
    latest.current = { passwordStrengthLevel, isPasswordVisible };
    control.current?.update(latest.current);
  }, [passwordStrengthLevel, isPasswordVisible]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let cancelled = false;
    const abort = new AbortController();
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      void import('./createPasswordRacer').then(module => {
        if (cancelled) return null;
        return module.createPasswordRacer(element, quality, abort.signal, () => { if (!cancelled) setStatus('fallback'); });
      }).then(scene => {
        if (!scene) return;
        if (cancelled) { scene.dispose(); return; }
        control.current = scene;
        scene.update(latest.current);
        setStatus('ready');
      }).catch(() => {
        if (!cancelled) setStatus('fallback');
      });
    }, { rootMargin: '120px' });
    observer.observe(element);
    return () => {
      cancelled = true;
      abort.abort();
      observer.disconnect();
      control.current?.dispose();
      control.current = null;
    };
  }, [quality]);

  return <div className="password-racer" aria-hidden="true" data-strength={passwordStrengthLevel} data-visible={isPasswordVisible} data-status={status}>
    <div className="password-racer-stage" ref={host}>
      {status !== 'ready' && <img className="password-racer-poster" src={`${import.meta.env.BASE_URL}models/password-racer/poster.webp`} alt="" width="1440" height="675" />}
    </div>
  </div>;
}
