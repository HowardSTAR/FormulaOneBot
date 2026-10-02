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
    <p><Link className="ui-action-link" to={`/history?kind=drivers&ids=${encodeURIComponent(driverId)}`}>Как менялось место по сезонам →</Link></p>
  </section>;
}
