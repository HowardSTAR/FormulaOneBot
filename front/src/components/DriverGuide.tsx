import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../helpers/api';
import { GlossaryText } from './GlossaryText';

type Guide = { intro: string; character: string; watch: string; source: string; note: string; checked_at: string };
export function DriverGuide({ driverId }: { driverId: string }) {
  const [guide, setGuide] = useState<Guide | null>(null);
  useEffect(() => {
    let active = true;
    apiRequest<{ guide: Guide | null }>('/api/driver-guide', { driverId })
      .then(data => { if (active) setGuide(data.guide); }).catch(() => { if (active) setGuide(null); });
    return () => { active = false; };
  }, [driverId]);
  return <section className="driver-guide">
    {guide && <details><summary>Знакомство с пилотом · для новичков</summary>
      <p><GlossaryText>{guide.intro}</GlossaryText></p>
      <h3>Характер выступлений</h3><p><GlossaryText>{guide.character}</GlossaryText></p>
      <h3>На что смотреть в гонке</h3><p><GlossaryText>{guide.watch}</GlossaryText></p>
      <p className="history-note">{guide.note}</p>
      <a className="ui-action-link" href={guide.source} target="_blank" rel="noreferrer">Официальная биография Formula 1 →</a>
      <p className="history-note">Справка проверена: {guide.checked_at}</p>
    </details>}
    <p><Link className="ui-action-link driver-history-link" to={`/history?kind=drivers&ids=${encodeURIComponent(driverId)}`}><svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4v16h16M7 15l4-5 4 3 5-7" /><path d="M16 6h4v4" /></svg><span>Как менялось место по сезонам</span><svg className="driver-history-chevron" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m9 5 7 7-7 7" /></svg></Link></p>
  </section>;
}
