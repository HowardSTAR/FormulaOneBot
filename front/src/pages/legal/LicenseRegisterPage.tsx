import { Link, useLocation } from 'react-router-dom';
import thirdParty from '../../../../THIRD_PARTY_NOTICES.md?raw';
import assets from '../../../../ASSET_LICENSES.md?raw';
export default function LicenseRegisterPage() {
  const isAssets = useLocation().pathname === '/legal/assets';
  const content = isAssets ? assets : thirdParty;
  // Render plain text, never executable HTML from a document.
  return <article className="legal-page"><Link to="/legal/ip">← Интеллектуальная собственность</Link>
    <h1>{isAssets ? 'Реестр материалов' : 'Сторонние компоненты'}</h1>
    <p>Реестр проекта на языке оригинала. Наличие файла в проекте само по себе не подтверждает права на его публикацию.</p>
    <div className="ui-legal-register">{content}</div>
  </article>;
}
