import { useMemo, useState } from "react";
import { BackButton } from "../../components/BackButton";
import {
  GLOSSARY_ITEMS,
  type GlossaryCategory,
  type GlossaryItem,
} from "../../constants/glossaryData";
import "./wiki.css";

type CategoryFilter = "all" | GlossaryCategory | "racing-rules";
type AlphabetKind = "ru" | "en";

type FilterOption = {
  id: CategoryFilter;
  label: string;
  categories?: readonly GlossaryCategory[];
};

const FILTERS: readonly FilterOption[] = [
  { id: "all", label: "Все" },
  { id: "general", label: "Общее", categories: ["general"] },
  { id: "tactics", label: "Тактика", categories: ["tactics"] },
  { id: "car", label: "Болид", categories: ["car"] },
  { id: "racing-rules", label: "Гонка и правила", categories: ["racing", "rules"] },
];

const CATEGORY_LABELS: Record<GlossaryCategory, string> = {
  general: "Общее",
  tactics: "Тактика",
  car: "Болид",
  racing: "Гонка",
  rules: "Правила",
};

const RU_ALPHABET = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ".split("");
const EN_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const collator = new Intl.Collator("ru", { sensitivity: "base" });

function normalizeSearch(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ё/g, "е")
    .toLocaleLowerCase("ru-RU")
    .trim();
}

function firstLetter(value: string): string {
  return value.trim().charAt(0).toLocaleUpperCase("ru-RU");
}

function matchesLetter(item: GlossaryItem, letter: string, kind: AlphabetKind): boolean {
  const source = kind === "ru" ? item.termRu : item.termEn;
  return firstLetter(source) === letter;
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

function BulbIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 18h6M10 21h4" />
      <path d="M8.2 14.5A6 6 0 1 1 15.8 14.5c-1 .8-1.4 1.5-1.4 2.5H9.6c0-1-.4-1.7-1.4-2.5Z" />
    </svg>
  );
}

export default function WikiPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<CategoryFilter>("all");
  const normalizedQuery = normalizeSearch(query);

  const filteredItems = useMemo(() => {
    const currentFilter = FILTERS.find((item) => item.id === category);
    return [...GLOSSARY_ITEMS]
      .filter((item) => {
        const matchesCategory = !currentFilter?.categories
          || currentFilter.categories.includes(item.category);
        if (!matchesCategory) return false;
        if (!normalizedQuery) return true;
        const haystack = normalizeSearch(
          `${item.termRu} ${item.termEn} ${item.definition} ${item.example ?? ""}`,
        );
        return haystack.includes(normalizedQuery);
      })
      .sort((left, right) => collator.compare(left.termRu, right.termRu));
  }, [category, normalizedQuery]);

  const resetFilters = () => {
    setQuery("");
    setCategory("all");
  };

  const scrollToLetter = (letter: string, kind: AlphabetKind) => {
    const item = filteredItems.find((candidate) => matchesLetter(candidate, letter, kind));
    if (!item) return;
    document.getElementById(`glossary-${item.id}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const renderAlphabet = (
    title: string,
    letters: readonly string[],
    kind: AlphabetKind,
  ) => (
    <div className="wiki-alphabet-row">
      <span>{title}</span>
      <div>
        {letters.map((letter) => {
          const available = filteredItems.some((item) => matchesLetter(item, letter, kind));
          return (
            <button
              key={`${kind}-${letter}`}
              type="button"
              disabled={!available}
              onClick={() => scrollToLetter(letter, kind)}
              aria-label={`Перейти к терминам на ${letter}`}
            >
              {letter}
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="wiki-page">
      <BackButton fallback="/" />

      <header className="wiki-hero">
        <div className="wiki-hero-copy">
          <span className="wiki-kicker">F1 Academy · сезон 2026</span>
          <h1>Wiki для<br /><em>новичков</em></h1>
          <p>
            Термины Формулы-1 без сложных формулировок — от андерката
            до активной аэродинамики.
          </p>
        </div>
        <div className="wiki-hero-stat" aria-label={`${GLOSSARY_ITEMS.length} терминов`}>
          <strong>{String(GLOSSARY_ITEMS.length).padStart(2, "0")}</strong>
          <span>терминов<br />в базе</span>
        </div>
      </header>

      <section className="wiki-controls" aria-label="Поиск и фильтры">
        <label className="wiki-search">
          <span className="sr-only">Поиск по глоссарию</span>
          <SearchIcon />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти термин на русском или английском"
            autoComplete="off"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Очистить поиск">
              ×
            </button>
          )}
        </label>

        <div className="wiki-filters" role="group" aria-label="Категории терминов">
          {FILTERS.map((filter) => (
            <button
              key={filter.id}
              type="button"
              className={category === filter.id ? "active" : ""}
              aria-pressed={category === filter.id}
              onClick={() => setCategory(filter.id)}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="wiki-alphabet" aria-label="Алфавитный указатель">
          {renderAlphabet("А—Я", RU_ALPHABET, "ru")}
          {renderAlphabet("A—Z", EN_ALPHABET, "en")}
        </div>
      </section>

      <div className="wiki-results-head" aria-live="polite">
        <div>
          <span>Словарь</span>
          <strong>{filteredItems.length} {filteredItems.length === 1 ? "термин" : "терминов"}</strong>
        </div>
        {filteredItems.length > 0 && (query || category !== "all") && (
          <button type="button" onClick={resetFilters}>Сбросить фильтры</button>
        )}
      </div>

      {filteredItems.length > 0 ? (
        <section className="wiki-grid" aria-label="Термины Формулы-1">
          {filteredItems.map((item, index) => (
            <article
              id={`glossary-${item.id}`}
              className={`wiki-card category-${item.category}`}
              key={item.id}
            >
              <div className="wiki-card-top">
                <span className="wiki-card-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="wiki-category">{CATEGORY_LABELS[item.category]}</span>
              </div>
              <h2>{item.termRu}</h2>
              <span className="wiki-term-en">{item.termEn}</span>
              <p>{item.definition}</p>
              {item.example && (
                <div className="wiki-example">
                  <span><BulbIcon /></span>
                  <div><strong>Простой пример</strong><p>{item.example}</p></div>
                </div>
              )}
            </article>
          ))}
        </section>
      ) : (
        <section className="wiki-empty">
          <div aria-hidden>?</div>
          <span>Ничего не найдено</span>
          <h2>Попробуйте другой запрос</h2>
          <p>Проверьте написание или верните все категории.</p>
          <button type="button" onClick={resetFilters}>Сбросить фильтры</button>
        </section>
      )}
    </div>
  );
}
