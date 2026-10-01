import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

export function NotFoundPage() {
  return <section className="ui-not-found"><h1>Страница не найдена</h1>
    <p>Возможно, адрес устарел или содержит опечатку. Выберите нужный раздел.</p>
    <div className="ui-feedback-actions"><Link to="/">На главную</Link><Link to="/season">Открыть календарь</Link></div>
  </section>;
}

export function RouteErrorPage() {
  const error = useRouteError();
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />;
  return <section className="ui-not-found" role="alert"><h1>Не удалось открыть страницу</h1>
    <p>Попробуйте загрузить её снова. Если ошибка повторится, вернитесь на главную.</p>
    <div className="ui-feedback-actions"><button type="button" onClick={() => window.location.reload()}>Повторить</button><Link to="/">На главную</Link></div>
  </section>;
}
