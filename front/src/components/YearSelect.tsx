import { useState, useRef, useEffect } from "react";

type YearSelectProps = {
  value: number;
  onChange: (year: number) => void;
  minYear: number;
  maxYear: number;
  placeholder?: string;
  showCurrentYearBtn?: boolean;
  className?: string;
};

function generateYears(min: number, max: number): number[] {
  const years: number[] = [];
  for (let y = max; y >= min; y--) years.push(y);
  return years;
}

export function YearSelect({
  value,
  onChange,
  minYear,
  maxYear,
  placeholder = "Введи год",
  showCurrentYearBtn = true,
  className = "",
}: YearSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const allYears = generateYears(minYear, maxYear);
  const filteredYears = query.trim()
    ? allYears.filter((y) => String(y).includes(query.trim()))
    : allYears;

  const currentYear = new Date().getFullYear();

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (
        inputRef.current &&
        !inputRef.current.contains(target) &&
        listRef.current &&
        !listRef.current.contains(target)
      ) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (year: number) => {
    onChange(year);
    setOpen(false);
    setQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent, year?: number) => {
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
      inputRef.current?.blur();
    } else if (e.key === "Enter" && year !== undefined) {
      handleSelect(year);
    }
  };

  return (
    <div className={`year-select-wrapper ${open ? "open" : ""} ${className}`}>
      <div className="search-container year-select-container">
        <div className="year-select-input-wrap">
          <input
            ref={inputRef}
            type="text"
            inputMode="numeric"
            className="search-input year-select-input"
            placeholder={placeholder}
            value={open ? query : String(value)}
            onChange={(e) => {
              const v = e.target.value;
              setQuery(v);
              if (!open) setOpen(true);
              if (/^\d{4}$/.test(v)) {
                const y = parseInt(v, 10);
                if (y >= minYear && y <= maxYear) handleSelect(y);
              }
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && filteredYears.length === 1) {
                e.preventDefault();
                handleSelect(filteredYears[0]);
              }
            }}
          />
          <div
            className="year-select-arrow"
            onClick={() => setOpen(!open)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && setOpen(!open)}
            aria-label={open ? "Закрыть" : "Открыть"}
          />
        </div>
        {showCurrentYearBtn && (
          <button
            type="button"
            className="current-year-btn"
            onClick={() => handleSelect(currentYear)}
          >
            {currentYear}
          </button>
        )}
      </div>

      {open && (
        <div
          ref={listRef}
          className="year-select-dropdown"
          role="listbox"
        >
          {filteredYears.length === 0 ? (
            <div className="year-select-empty">Ничего не найдено</div>
          ) : (
            filteredYears.map((y) => (
              <div
                key={y}
                className={`year-select-option ${y === value ? "selected" : ""}`}
                onClick={() => handleSelect(y)}
                onKeyDown={(e) => handleKeyDown(e, y)}
                role="option"
                aria-selected={y === value}
                tabIndex={0}
              >
                {y}
                {y === currentYear && <span className="year-select-badge">сейчас</span>}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
