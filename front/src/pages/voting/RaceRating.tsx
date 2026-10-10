import { useState } from 'react';
import './race-rating.css';

const ratingLabels = ['Не понравилась', 'Могло быть лучше', 'Неплохая гонка', 'Отличная гонка', 'Незабываемая гонка'];

export function RaceRating({ value = 0, saving, onChange }: {
  value?: number;
  saving: boolean;
  onChange: (rating: number) => void;
}) {
  const [preview, setPreview] = useState(0);
  const displayed = preview || value;

  return (
    <div className="race-rating" aria-busy={saving}>
      <div className="race-rating-stars" role="group" aria-label="Оценка гонки"
        onPointerLeave={() => setPreview(0)} onBlur={() => setPreview(0)}>
        {[1, 2, 3, 4, 5].map(rating => (
          <button key={rating} type="button"
            className={`race-rating-star${rating <= displayed ? ' is-filled' : ''}`}
            aria-label={`Оценить гонку на ${rating} из 5`} aria-pressed={value === rating}
            data-analytics-action="vote_submit" disabled={saving}
            onPointerEnter={event => { if (event.pointerType === 'mouse') setPreview(rating); }}
            onFocus={() => setPreview(rating)}
            onClick={() => { setPreview(0); onChange(rating); }}>
            <svg viewBox="0 0 32 32" aria-hidden="true">
              <path d="m16 3.5 3.84 7.78 8.59 1.25-6.22 6.06 1.47 8.56L16 23.11l-7.68 4.04 1.47-8.56-6.22-6.06 8.59-1.25Z" />
            </svg>
          </button>
        ))}
      </div>
      <div className="race-rating-caption" role="status" aria-live="polite">
        <span className="race-rating-score">{displayed || '—'}<small> / 5</small></span>
        <span className="race-rating-description">
          <span>{saving ? 'Сохраняем оценку…' : preview ? 'Ваша оценка' : value ? 'Ваша оценка сохранена' : 'Как вам гонка?'}</span>
          <strong>{displayed ? ratingLabels[displayed - 1] : 'Выберите звёзды'}</strong>
        </span>
      </div>
    </div>
  );
}
