import { SelectField } from './CustomSelect';
type YearSelectProps = {
  value: number;
  onChange: (year: number) => void;
  minYear: number;
  maxYear: number;
  placeholder?: string;
  showCurrentYearBtn?: boolean;
  className?: string;
  ariaLabel?: string;
};

export function YearSelect({
  value,
  onChange,
  minYear,
  maxYear,
  showCurrentYearBtn = true,
  className = "",
  ariaLabel = "Сезон",
}: YearSelectProps) {
  const years = Array.from({ length: Math.max(0, maxYear - minYear + 1) }, (_, index) => maxYear - index);
  const currentYear = new Date().getFullYear();

  return <div className={`year-select-wrapper ${className}`}>
    <div className="search-container year-select-container">
      <SelectField aria-label={ariaLabel} className="year-select-input" value={value}
        onChange={event => onChange(Number(event))}>
        {years.map(year => <option key={year} value={year}>{year}</option>)}
      </SelectField>
      {showCurrentYearBtn && currentYear >= minYear && currentYear <= maxYear && <button type="button" className="current-year-btn"
        aria-label={`Текущий сезон ${currentYear}`} onClick={() => onChange(currentYear)}>Текущий</button>}
    </div>
  </div>;
}
