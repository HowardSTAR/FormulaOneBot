import { Link } from "react-router-dom";

export function PageFeedback({ message = "Не удалось получить данные. Проверьте соединение и попробуйте снова.", retry, parent }: { message?: string; retry?: () => void; parent?: { to: string; label: string } }) {
  return <section className="ui-feedback" role="alert">
    <h2>Не удалось загрузить</h2><p>{message}</p>
    <div className="ui-feedback-actions">
      {retry && <button type="button" className="action-button" onClick={retry}>Повторить</button>}
      {parent && <Link to={parent.to}>{parent.label}</Link>}
    </div>
  </section>;
}
