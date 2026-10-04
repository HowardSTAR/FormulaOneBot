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
      {children || <><span aria-hidden>←</span><span>Назад</span></>}
    </button>
  );
}
