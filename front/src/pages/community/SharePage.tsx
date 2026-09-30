import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../helpers/api';
import { rememberInvitation, sharingEvent, type ShareCard } from '../../helpers/sharing';
import { BackButton } from '../../components/BackButton';
import './community.css';

export default function SharePage() {
  const {token = ''} = useParams(), navigate = useNavigate();
  const [result, setResult] = useState<{card?: ShareCard; error?: string}>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    apiRequest<ShareCard>(`/api/engagement/shares/${token}`).then(card => {
      if (!active) return;
      setResult({card}); rememberInvitation(token); void sharingEvent(token, 'arrival');
    }).catch(() => {if (active) setResult({error: 'Ссылка истекла или отозвана. Можно начать свой прогноз или заезд.'});});
    return () => {active = false;};
  }, [token]);
  async function accept() {
    if (busy) return;
    setBusy(true);
    try {
      const {path} = await apiRequest<{path: string}>(`/api/engagement/shares/${token}/destination`);
      // Server supplies only an allowlisted local route, never an arbitrary URL.
      if (!/^\/(race-game|predictions|history|race-results)([?#]|$)/.test(path)) throw new Error('Некорректный переход');
      navigate(path);
    } catch {setResult({error: 'Приглашение больше не действует.'}); setBusy(false);}
  }
  return <main className="community-page"><BackButton>← Назад</BackButton>
    {!result.card ? <section className="community-card"><p role={result.error ? 'alert' : 'status'}>{result.error || 'Открываем приглашение…'}</p>{result.error && <Link to="/community">Прогнозы и соревнования →</Link>}</section> : <section className="community-card share-landing">
      <small>Приглашение в F1Hub</small><h1>{result.card.title}</h1>
      <p>{result.card.subtitle}</p>
      <img src={result.card.image_url} alt={`${result.card.subtitle}: ${result.card.headline}`} />
      <h2>{result.card.headline}</h2>{result.card.lines.map((line, i) => <p key={i}>{line}</p>)}
      {result.card.provisional && <p>Данные на момент создания карточки; результат предварительный.</p>}
      <button className="community-primary" disabled={busy} onClick={() => void accept()}>{busy ? 'Открываем…' : result.card.cta}</button>
      <p className="community-note">Просмотр не требует регистрации. Вход понадобится для сохранения прогноза или игрового результата. Вступление в лигу — только после подтверждения.</p>
      {result.card.mini_app_url && <a href={result.card.mini_app_url}>Открыть в Telegram Mini App →</a>}
    </section>}
  </main>;
}
