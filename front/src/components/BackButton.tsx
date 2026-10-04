import { useNavigate } from "react-router-dom";

type BackButtonProps = {
  fallback?: string;
  children?: React.ReactNode;
  className?: string;
};

/** Кнопка «Назад» — возвращает на предыдущую страницу в истории. */
export function BackButton({ fallback, children, className = "btn-back" }: BackButtonProps) {
  const navigate = useNavigate();

  const handleClick = () => {
    if (Number(window.history.state?.idx) > 0) {
      navigate(-1);
    } else {
      navigate(fallback ?? "/");
    }
  };

  return (
    <button type="button" data-analytics-action="back" className={className} onClick={handleClick} aria-label="Назад">
      <svg className="back-button-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m12 5-7 7 7 7M5 12h14" /></svg>
      <span className="back-button-label">{children || <><span aria-hidden>←</span><span>Назад</span></>}</span>
    </button>
  );
}
