import { useEffect } from 'react';
import { isRouteErrorResponse, useRouteError } from 'react-router-dom';
import { ThemeToggle } from './ThemeToggle';
import recoveryPitStop from '../assets/illustrations/recovery-pit-stop.webp';
import './route-error-page.css';

/** A short pit-stop pause gives the recovery screen a racing context. */
function RecoveryIllustration() {
  return <div className="route-recovery-art" aria-hidden="true">
    <img src={recoveryPitStop} alt="" width="1152" height="768" decoding="async" />
  </div>;
}

function RecoveryPage({ notFound = false, standalone = false }: { notFound?: boolean; standalone?: boolean }) {
  const title = notFound ? 'Страница не найдена' : 'Не удалось открыть страницу';
  useEffect(() => {
    if (!standalone) return;
    const previous = document.title;
    document.title = `${title} · TurboTears`;
    return () => { document.title = previous; };
  }, [standalone, title]);
  const Content = standalone ? 'main' : 'section';
  return <div className={`route-recovery${standalone ? ' route-recovery--standalone' : ''}`}>
    {standalone && <header className="route-recovery-header">
      <a className="route-recovery-brand" href="/" aria-label="TurboTears — главная"><span>Turbo</span><span>Tears</span></a>
      <ThemeToggle />
    </header>}
    <Content className="route-recovery-content" aria-labelledby="route-recovery-title">
      <div className="route-recovery-copy">
        <div role={notFound ? undefined : 'alert'}><h1 id="route-recovery-title">{title}</h1>
        <p>{notFound ? 'Возможно, адрес устарел или содержит опечатку. Вернитесь на главную или выберите этап в календаре.' : 'Попробуйте загрузить её снова. Если ошибка повторится, вернитесь на главную.'}</p></div>
        <div className="route-recovery-actions">
          {notFound ? <a className="route-recovery-primary" href="/">На главную</a> : <button className="route-recovery-primary" type="button" onClick={() => window.location.reload()}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 4v6h-6M4 20v-6h6M20 10a8 8 0 0 0-14-5M4 14a8 8 0 0 0 14 5" /></svg>Повторить загрузку</button>}
          <a className="route-recovery-secondary" href={notFound ? '/season' : '/'}>{notFound ? 'Открыть календарь' : 'На главную'}<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg></a>
        </div>
      </div>
      <RecoveryIllustration />
    </Content>
  </div>;
}

export function NotFoundPage({ standalone = false }: { standalone?: boolean }) {
  return <RecoveryPage notFound standalone={standalone} />;
}

export function RouteErrorPage() {
  const error = useRouteError();
  return <RecoveryPage notFound={isRouteErrorResponse(error) && error.status === 404} standalone />;
}
