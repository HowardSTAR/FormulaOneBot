import { Link, useLocation } from 'react-router-dom';
import thirdParty from '../../../../THIRD_PARTY_NOTICES.md?raw';
import assets from '../../../../ASSET_LICENSES.md?raw';
import './legal.css';
export default function LicenseRegisterPage() {
  const isAssets = useLocation().pathname === '/legal/assets';
  const content = isAssets ? assets : thirdParty;
  const sections = content.split(/^## /m).map(part => {
    const [heading,...lines] = part.replace(/^# /,'').split('\n');
    return {heading, paragraphs:lines.join('\n').trim().split(/\n\n+/)};
  });
  return <article className="legal-page"><Link to="/legal/ip">← Интеллектуальная собственность</Link>
    <h1>{isAssets ? 'Реестр материалов' : 'Сторонние компоненты'}</h1>
    <p>Источники и лицензии компонентов и материалов. Подробности сохранены на языке оригинала.</p>
    <details><summary>Открыть подробный реестр</summary><div className="ui-legal-register">{sections.map((section,i)=><section key={i}><h2>{section.heading}</h2>{section.paragraphs.map((text,j)=><p key={j}>{text.replace(/`/g,'').replace(/<(https?:\/\/[^>]+)>/g,'$1')}</p>)}</section>)}</div></details>
  </article>;
}
