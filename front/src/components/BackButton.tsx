import { useNavigate } from "react-router-dom";

type BackButtonProps = {
  fallback?: string;
  children?: React.ReactNode;
  className?: string;
};

/** Кнопка «Назад» — возвращает на предыдущую страницу в истории. */
export function BackButton({ fallback, className = "btn-back" }: BackButtonProps) {
  const navigate = useNavigate();

  const handleClick = () => {
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate(fallback ?? "/");
    }
  };

  return (
    <button type="button" className={className} onClick={handleClick} aria-label="Назад">
      <span aria-hidden>←</span><span>Назад</span>
    </button>
  );
}
