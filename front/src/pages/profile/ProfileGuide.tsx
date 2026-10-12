import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { apiRequest } from '../../helpers/api';
import { ONBOARDING_CHANGED } from '../../helpers/onboarding';
import { PROFILE_GUIDE_START, profileGuideSteps, emailVerificationStep, readProfileGuide, saveProfileGuide, type ProfileGuideStatus } from '../../helpers/profileGuide';
import '../../components/first-visit-guide.css';
import './profile-guide.css';

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export default function ProfileGuide({ userId, seen, needsEmailVerification = false }: { userId: number; seen: boolean; needsEmailVerification?: boolean }) {
  const steps = useMemo(() => needsEmailVerification ? [emailVerificationStep, ...profileGuideSteps] : profileGuideSteps, [needsEmailVerification]);
  const [stage, setStage] = useState<number | null>(null);
  const panel = useRef<HTMLElement>(null);
  const started = useRef(false);
  const active = stage !== null;
  const finish = useCallback((status: ProfileGuideStatus) => {
    setStage(null); saveProfileGuide(userId,status);
    void apiRequest('/api/profiles/me/guide',{ status },'PATCH').catch(() => { /* Retry the saved local receipt on a later visit. */ });
  }, [userId]);
  useEffect(() => {
    const local = readProfileGuide(userId);
    if(!seen && local)void apiRequest('/api/profiles/me/guide',{ status: local },'PATCH').catch(() => {});
    const maybeStart = () => {
      if(started.current || seen || local || document.documentElement.dataset.onboardingActive
        || document.querySelector('dialog[open]'))return;
      started.current=true;setStage(0);
    };
    const replay = (event: Event) => {
      if((event as CustomEvent<{userId:number}>).detail?.userId !== userId
        || document.documentElement.dataset.onboardingActive || document.querySelector('dialog[open]'))return;
      started.current=true;setStage(0);
    };
    const observer = new MutationObserver(maybeStart);
    observer.observe(document.documentElement,{attributes:true,attributeFilter:['data-onboarding-active']});
    observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});
    window.addEventListener(PROFILE_GUIDE_START,replay);
    const frame=requestAnimationFrame(maybeStart);
    return () => { cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener(PROFILE_GUIDE_START,replay); };
  }, [userId,seen]);
  useLayoutEffect(() => {
    if(!active)return;
    const root=document.documentElement, preview=document.querySelector<HTMLElement>('.app-content');
    const previousFocus=document.activeElement, overflow=root.style.overflow;
    const oldHeight=root.style.getPropertyValue('--onboarding-panel-height');
    const previousScroll=preview?.scrollTop;
    root.dataset.onboardingActive='profile';root.dataset.onboardingPhase='ready';root.dataset.profileGuideActive='true';
    root.style.overflow='hidden';
    const measure=()=>root.style.setProperty('--onboarding-panel-height',`${panel.current?.offsetHeight || 230}px`);
    measure();const observer=new ResizeObserver(measure);if(panel.current)observer.observe(panel.current);
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape' && !document.querySelector('dialog[open]'))finish('skipped');};
    window.addEventListener('keydown',escape);window.dispatchEvent(new Event(ONBOARDING_CHANGED));
    panel.current?.focus({preventScroll:true});
    return () => {
      observer.disconnect();window.removeEventListener('keydown',escape);
      delete root.dataset.onboardingActive;delete root.dataset.onboardingPhase;delete root.dataset.profileGuideActive;
      root.style.overflow=overflow;
      if(oldHeight)root.style.setProperty('--onboarding-panel-height',oldHeight);else root.style.removeProperty('--onboarding-panel-height');
      window.dispatchEvent(new Event(ONBOARDING_CHANGED));
      if(preview && previousScroll !== undefined)preview.scrollTo({top:previousScroll,behavior:'instant'});
      if(previousFocus instanceof HTMLElement && previousFocus.isConnected)previousFocus.focus({preventScroll:true});
    };
  }, [active,finish]);
  useLayoutEffect(() => {
    if(stage === null)return;
    const step=steps[stage];
    const preview=document.querySelector<HTMLElement>('.app-content');
    let target: HTMLElement | null = null;
    const prepare=()=>{
      const next=document.querySelector<HTMLElement>(step.target);
      if(!next || next===target)return;
      target?.classList.remove('first-visit-highlight');target=next;target.classList.add('first-visit-highlight');
      if(preview){const rect=target.getBoundingClientRect(),parent=preview.getBoundingClientRect();preview.scrollTo({top:Math.max(0,preview.scrollTop+rect.top-parent.top-16),behavior:reduced()?'instant':'smooth'});}
      panel.current?.focus({preventScroll:true});
    };
    const timer=requestAnimationFrame(prepare);
    const observer=new MutationObserver(prepare);
    const scope=document.querySelector('.user-profile-page');if(scope)observer.observe(scope,{childList:true,subtree:true});
    return () => {cancelAnimationFrame(timer);observer.disconnect();target?.classList.remove('first-visit-highlight');};
  }, [stage, steps]);
  if(stage === null)return null;
  const step=steps[stage];
  return createPortal(<aside ref={panel} className="first-visit-guide profile-guide" tabIndex={-1} aria-label="Знакомство с профилем" aria-describedby="profile-guide-description">
    <div className="first-visit-top"><span>ТВОЙ ПРОФИЛЬ · {stage+1} / {steps.length}</span><button type="button" className="first-visit-close" aria-label="Закрыть знакомство с профилем" onClick={()=>finish('skipped')}>×</button></div>
    <div className="first-visit-progress" aria-hidden="true">{steps.map((item,index)=><i key={item.title} className={index<=stage?'is-done':''} />)}</div>
    <div className="first-visit-copy" key={step.title} aria-live="polite" aria-atomic="true"><h2>{step.title}</h2><p id="profile-guide-description">{step.text}</p></div>
    <div className="first-visit-actions">{stage>0 && <button type="button" className="first-visit-secondary" aria-label="Предыдущая функция профиля" onClick={()=>setStage(stage-1)}>←</button>}
      <button type="button" className="first-visit-primary" onClick={()=>stage === steps.length-1?finish('completed'):setStage(stage+1)}>{stage === steps.length-1?'Готово, это мой профиль':'Дальше →'}</button></div>
    <small className="first-visit-note">Можно прокручивать профиль и пробовать его функции.</small>
  </aside>,document.body);
}
