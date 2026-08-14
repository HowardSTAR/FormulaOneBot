import { Link } from "react-router-dom";

export function LegalFooter() {
  return (
    <footer className="legal-footer">
      <div className="legal-footer-heading">
        <strong>TurboTears</strong>
        <span>Independent race intelligence</span>
      </div>
      <p>
        Независимый некоммерческий информационный проект для поклонников автоспорта.
        Проект не является официальным продуктом и не связан с Formula One Group,
        FIA, командами, гонщиками или организаторами этапов.
      </p>
      <p lang="en" className="legal-footer-trademark">
        This website is unofficial and is not associated in any way with the Formula 1
        companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP,
        GRAND PRIX and related marks are trade marks of Formula One Licensing B.V.
      </p>
      <nav aria-label="Правовая информация">
        <Link to="/privacy">Конфиденциальность</Link>
        <Link to="/terms">Условия использования</Link>
        <Link to="/legal/ip">Интеллектуальная собственность</Link>
        <Link to="/about/data">Источники данных</Link>
        <Link to="/account/delete">Удаление данных</Link>
        <Link to="/contact-admin">Связаться</Link>
      </nav>
      <small>© {new Date().getFullYear()} TurboTears. Исходный код и сторонние материалы лицензируются отдельно.</small>
    </footer>
  );
}
