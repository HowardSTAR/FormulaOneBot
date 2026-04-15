import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BackButton } from "../../components/BackButton";
import { hapticImpact, hapticSelection } from "../../helpers/telegram";
import { apiRequest } from "../../helpers/api";

type ReactionTab = "game" | "leaderboard";
type GameMode = "timed" | "endless";
type Difficulty = "easy" | "medium" | "hard";
type GameStatus = "idle" | "running" | "finished";

type LeaderboardProfile = {
  display_name: string;
  participate: boolean;
  prompt_seen: boolean;
};

type ReflexLeaderboardEntry = {
  place: number;
  telegram_id: number;
  name: string;
  score: number;
  time_ms: number;
  mode: GameMode;
  difficulty: Difficulty;
  is_me: boolean;
};

type ReflexLeaderboardResponse = {
  entries: ReflexLeaderboardEntry[];
  me: ReflexLeaderboardEntry | null;
};

const MODE_OPTIONS: { id: GameMode; label: string }[] = [
  { id: "timed", label: "По времени (10 сек)" },
  { id: "endless", label: "Бесконечный (10 плиток)" },
];

const DIFFICULTY_OPTIONS: { id: Difficulty; label: string; size: number }[] = [
  { id: "easy", label: "Простой 3x3", size: 3 },
  { id: "medium", label: "Средний 4x4", size: 4 },
  { id: "hard", label: "Сложный 5x5", size: 5 },
];

const TIMED_DURATION_MS = 10_000;
const ENDLESS_TARGET = 10;

function formatSecondsMs(ms: number): string {
  return (ms / 1000).toFixed(3);
}

function formatRemaining(ms: number): string {
  return `${Math.max(0, ms / 1000).toFixed(1)}с`;
}

function pickNextTile(total: number, current: number | null): number {
  if (total <= 1) return 0;
  let next = Math.floor(Math.random() * total);
  while (current != null && next === current) {
    next = Math.floor(Math.random() * total);
  }
  return next;
}

function ReflexGridGamePage() {
  const [activeTab, setActiveTab] = useState<ReactionTab>("game");
  const [showGameOptions, setShowGameOptions] = useState(false);
  const [mode, setMode] = useState<GameMode>("timed");
  const [difficulty, setDifficulty] = useState<Difficulty>("easy");
  const [status, setStatus] = useState<GameStatus>("idle");
  const [activeTile, setActiveTile] = useState<number | null>(0);
  const [score, setScore] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [remainingMs, setRemainingMs] = useState(TIMED_DURATION_MS);
  const [profile, setProfile] = useState<LeaderboardProfile>({
    display_name: "",
    participate: false,
    prompt_seen: false,
  });
  const [settingsName, setSettingsName] = useState("");
  const [settingsParticipate, setSettingsParticipate] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [settingsError, setSettingsError] = useState("");
  const [isEditingSettings, setIsEditingSettings] = useState(false);
  const [showConfirmSave, setShowConfirmSave] = useState(false);
  const [leaderboard, setLeaderboard] = useState<ReflexLeaderboardResponse>({ entries: [], me: null });
  const [leaderboardLoading, setLeaderboardLoading] = useState(true);
  const [leaderboardError, setLeaderboardError] = useState("");
  const meRowRef = useRef<HTMLDivElement | null>(null);

  const rafIdRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const scoreRef = useRef(0);

  const boardSize = useMemo(
    () => DIFFICULTY_OPTIONS.find((item) => item.id === difficulty)?.size ?? 3,
    [difficulty]
  );
  const totalTiles = boardSize * boardSize;

  const clearGameLoop = useCallback(() => {
    if (rafIdRef.current != null) {
      window.cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  const resetBoard = useCallback(() => {
    clearGameLoop();
    startedAtRef.current = null;
    scoreRef.current = 0;
    setStatus("idle");
    setScore(0);
    setElapsedMs(0);
    setRemainingMs(TIMED_DURATION_MS);
    setActiveTile(pickNextTile(totalTiles, null));
  }, [clearGameLoop, totalTiles]);

  useEffect(() => {
    resetBoard();
  }, [mode, difficulty, resetBoard]);

  useEffect(() => clearGameLoop, [clearGameLoop]);

  useEffect(() => {
    scoreRef.current = score;
  }, [score]);

  const fetchLeaderboard = useCallback(async () => {
    try {
      setLeaderboardLoading(true);
      setLeaderboardError("");
      const data = await apiRequest<ReflexLeaderboardResponse>(
        "/api/reflex-grid-leaderboard",
        { mode, difficulty },
        "GET"
      );
      setLeaderboard(data);
    } catch (e) {
      setLeaderboardError(e instanceof Error ? e.message : "Не удалось загрузить таблицу лидеров");
    } finally {
      setLeaderboardLoading(false);
    }
  }, [difficulty, mode]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [profileData, leaderboardData] = await Promise.all([
          apiRequest<LeaderboardProfile>("/api/reaction-leaderboard/profile"),
          apiRequest<ReflexLeaderboardResponse>("/api/reflex-grid-leaderboard", { mode, difficulty }, "GET"),
        ]);
        if (cancelled) return;
        setProfile(profileData);
        setSettingsName(profileData.display_name || "");
        setSettingsParticipate(profileData.participate);
        setShowOnboarding(!profileData.prompt_seen);
        setLeaderboard(leaderboardData);
      } catch (e) {
        if (cancelled) return;
        setLeaderboardError(e instanceof Error ? e.message : "Не удалось загрузить данные игры");
      } finally {
        if (!cancelled) setLeaderboardLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [mode, difficulty]);

  useEffect(() => {
    if (activeTab !== "leaderboard") return;
    if (!meRowRef.current) return;
    meRowRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeTab, leaderboard]);

  const saveLeaderboardSettings = useCallback(
    async (options?: { fromOnboarding?: boolean }) => {
      const fromOnboarding = Boolean(options?.fromOnboarding);
      setIsSavingSettings(true);
      setSettingsSaved(false);
      setSettingsError("");
      try {
        const payload = {
          display_name: settingsName.trim(),
          participate: settingsParticipate,
          prompt_seen: true,
        };
        const data = await apiRequest<{ profile: LeaderboardProfile }>(
          "/api/reaction-leaderboard/profile",
          payload,
          "POST"
        );
        setProfile(data.profile);
        setSettingsName(data.profile.display_name);
        setSettingsParticipate(data.profile.participate);
        if (fromOnboarding) {
          setShowOnboarding(false);
        } else {
          setIsEditingSettings(false);
          setShowConfirmSave(false);
          setSettingsSaved(true);
          window.setTimeout(() => setSettingsSaved(false), 2200);
        }
        await fetchLeaderboard();
      } catch (e) {
        setSettingsError(e instanceof Error ? e.message : "Не удалось сохранить настройки");
      } finally {
        setIsSavingSettings(false);
      }
    },
    [fetchLeaderboard, settingsName, settingsParticipate]
  );

  const submitResult = useCallback(
    async (nextScore: number, nextTimeMs: number) => {
      if (!profile.participate) return;
      try {
        await apiRequest(
          "/api/reflex-grid-leaderboard/score",
          { mode, difficulty, score: nextScore, time_ms: Math.max(1, Math.round(nextTimeMs)) },
          "POST"
        );
        await fetchLeaderboard();
      } catch (e) {
        console.warn("Reflex grid leaderboard submit failed", e);
      }
    },
    [difficulty, fetchLeaderboard, mode, profile.participate]
  );

  const finishGame = useCallback(
    (finalScore: number, finalTimeMs: number) => {
      clearGameLoop();
      setStatus("finished");
      setElapsedMs(finalTimeMs);
      if (mode === "timed") {
        setRemainingMs(0);
      }
      void submitResult(finalScore, finalTimeMs);
    },
    [clearGameLoop, mode, submitResult]
  );

  const startLoop = useCallback(() => {
    const tick = () => {
      if (startedAtRef.current == null) return;
      const now = performance.now();
      const elapsed = now - startedAtRef.current;
      setElapsedMs(elapsed);
      if (mode === "timed") {
        const left = Math.max(0, TIMED_DURATION_MS - elapsed);
        setRemainingMs(left);
        if (left <= 0) {
          finishGame(scoreRef.current, TIMED_DURATION_MS);
          return;
        }
      }
      rafIdRef.current = window.requestAnimationFrame(tick);
    };
    rafIdRef.current = window.requestAnimationFrame(tick);
  }, [finishGame, mode]);

  const startGame = useCallback(() => {
    if (activeTile == null) return;
    setStatus("running");
    setScore(1);
    scoreRef.current = 1;
    setElapsedMs(0);
    setRemainingMs(TIMED_DURATION_MS);
    startedAtRef.current = performance.now();
    setActiveTile(pickNextTile(totalTiles, activeTile));
    startLoop();
  }, [activeTile, startLoop, totalTiles]);

  const handleHit = useCallback(() => {
    if (status !== "running") return;
    const nextScore = scoreRef.current + 1;
    setScore(nextScore);
    scoreRef.current = nextScore;
    hapticImpact("light");
    setActiveTile((prev) => pickNextTile(totalTiles, prev));

    if (mode === "endless" && nextScore >= ENDLESS_TARGET) {
      const finalTime = startedAtRef.current == null ? elapsedMs : performance.now() - startedAtRef.current;
      finishGame(nextScore, finalTime);
    }
  }, [elapsedMs, finishGame, mode, status, totalTiles]);

  const handleTileClick = (index: number) => {
    if (index !== activeTile) return;
    if (status === "idle") {
      hapticImpact("medium");
      startGame();
      return;
    }
    if (status === "running") {
      handleHit();
    }
  };

  const settingsChanged =
    settingsName.trim() !== (profile.display_name || "").trim() || settingsParticipate !== profile.participate;

  const currentMetricText =
    mode === "timed"
      ? `Попаданий: ${score}`
      : status === "running"
        ? `Цель: ${Math.min(score, ENDLESS_TARGET)}/${ENDLESS_TARGET}`
        : `Последний результат: ${score}/${ENDLESS_TARGET}`;

  const timerText = mode === "timed" ? formatRemaining(remainingMs) : `${formatSecondsMs(elapsedMs)}с`;

  const helperText =
    status === "running"
      ? "Жми только по подсвеченной плитке"
      : mode === "timed"
        ? "Тапни по подсвеченной плитке, потом за 10 секунд набери максимум"
        : "Тапни по подсвеченной плитке и закрой цель из 10 попаданий как можно быстрее";

  const myPlaceText = useMemo(() => {
    if (!leaderboard.me) return "Пока нет результата в таблице";
    if (mode === "timed") {
      return `Твое место: #${leaderboard.me.place} (${leaderboard.me.score} очков)`;
    }
    return `Твое место: #${leaderboard.me.place} (${formatSecondsMs(leaderboard.me.time_ms)} сек)`;
  }, [leaderboard.me, mode]);

  return (
    <>
      {showOnboarding && (
        <div className="reaction-modal-overlay">
          <div className="reaction-modal-card">
            <h3 className="reaction-modal-title">Таблица лидеров</h3>
            <p className="reaction-modal-text">Использовать это имя и участие для всех игр?</p>
            <input
              className="reaction-input"
              placeholder="Твое имя в таблице"
              value={settingsName}
              onChange={(e) => setSettingsName(e.target.value)}
              maxLength={32}
            />
            <div className="reaction-toggle-row">
              <button
                type="button"
                className={`reaction-toggle-btn ${settingsParticipate ? "active" : ""}`}
                onClick={() => setSettingsParticipate(true)}
              >
                Да
              </button>
              <button
                type="button"
                className={`reaction-toggle-btn ${!settingsParticipate ? "active" : ""}`}
                onClick={() => setSettingsParticipate(false)}
              >
                Нет
              </button>
            </div>
            <button
              type="button"
              className="reaction-settings-save"
              disabled={isSavingSettings}
              onClick={() => {
                void saveLeaderboardSettings({ fromOnboarding: true });
              }}
            >
              {isSavingSettings ? "Сохраняем..." : "Продолжить"}
            </button>
          </div>
        </div>
      )}

      {status === "finished" && (
        <div className="reaction-modal-overlay">
          <div className="reaction-modal-card reflex-finish-modal">
            <h3 className="reaction-modal-title">Результат попытки</h3>
            <div className="reflex-finish-score">{score}</div>
            <div className="reflex-finish-label">попаданий</div>
            <p className="reaction-modal-text" style={{ marginTop: 10 }}>
              {mode === "timed"
                ? "За 10 секунд"
                : `За ${formatSecondsMs(elapsedMs)} секунд до цели ${ENDLESS_TARGET}`}
            </p>
            <button type="button" className="reaction-settings-save" onClick={resetBoard}>
              Сыграть снова
            </button>
          </div>
        </div>
      )}

      <BackButton>← <span>На главную</span></BackButton>
      <h2 style={{ marginTop: 10, marginBottom: 10 }}>Reflex Grid</h2>
      <p className="reaction-subtitle">
        Режимы: 10 секунд на максимум или 10 попаданий на время. Сложность меняет размер поля.
      </p>

      <div className="segmented-tabs reaction-segmented">
        <div
          className="segmented-slider"
          style={{ transform: activeTab === "game" ? "translateX(0)" : "translateX(100%)" }}
          aria-hidden
        />
        <button type="button" className={`segmented-tab ${activeTab === "game" ? "active" : ""}`} onClick={() => setActiveTab("game")}>
          Игра
        </button>
        <button
          type="button"
          className={`segmented-tab ${activeTab === "leaderboard" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setActiveTab("leaderboard");
          }}
        >
          Лидеры
        </button>
      </div>

      <section className="reaction-slide">
        <div className="reaction-settings-card">
          <button
            type="button"
            className="reflex-options-toggle"
            onClick={() => setShowGameOptions((prev) => !prev)}
          >
            <span>
              Параметры игры: {MODE_OPTIONS.find((item) => item.id === mode)?.label} •{" "}
              {DIFFICULTY_OPTIONS.find((item) => item.id === difficulty)?.label}
            </span>
            <span className={`reflex-options-chevron ${showGameOptions ? "open" : ""}`}>⌄</span>
          </button>

          {showGameOptions && (
            <>
              <div className="reflex-filter-grid">
                {MODE_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={`reflex-filter-btn ${mode === option.id ? "active" : ""}`}
                    onClick={() => {
                      hapticSelection();
                      setMode(option.id);
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              <div className="reflex-filter-grid reflex-filter-grid-difficulty">
                {DIFFICULTY_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={`reflex-filter-btn ${difficulty === option.id ? "active" : ""}`}
                    onClick={() => {
                      hapticSelection();
                      setDifficulty(option.id);
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      {activeTab === "game" && (
        <>
          <div className="reaction-timer-card">
            <div className="reaction-main-time">{mode === "timed" ? timerText : `${formatSecondsMs(elapsedMs)}`}</div>
            <div className="reaction-time-unit">{mode === "timed" ? "До конца" : "Секунд"}</div>
            <div className="reaction-result" style={{ marginTop: 8 }}>{currentMetricText}</div>
          </div>

          <div className="reflex-grid" style={{ gridTemplateColumns: `repeat(${boardSize}, minmax(0, 1fr))` }}>
            {Array.from({ length: totalTiles }).map((_, index) => (
              <button
                key={`${difficulty}-${index}`}
                type="button"
                className={`reflex-tile ${index === activeTile ? "active" : ""}`}
                onClick={() => handleTileClick(index)}
                aria-label={`Плитка ${index + 1}`}
              />
            ))}
          </div>

          <button type="button" className="reaction-settings-edit" style={{ marginTop: 14 }} onClick={resetBoard}>
            Сыграть снова
          </button>
          <p className="reaction-helper">{helperText}</p>

          <section className="reaction-slide">
            <div className="reaction-settings-card">
              <div className="reaction-settings-title">Общий профиль лидерборда</div>
              {!isEditingSettings ? (
                <>
                  <p className="reaction-settings-caption">
                    Сейчас: {profile.participate ? "участвуешь" : "не участвуешь"} {profile.display_name ? `• ${profile.display_name}` : ""}
                  </p>
                  <button
                    type="button"
                    className="reaction-settings-edit"
                    onClick={() => {
                      setSettingsName(profile.display_name || "");
                      setSettingsParticipate(profile.participate);
                      setIsEditingSettings(true);
                      setShowConfirmSave(false);
                      setSettingsError("");
                    }}
                  >
                    Изменить настройки
                  </button>
                </>
              ) : (
                <>
                  <input
                    className="reaction-input"
                    placeholder="Имя в таблице"
                    value={settingsName}
                    onChange={(e) => setSettingsName(e.target.value)}
                    maxLength={32}
                  />
                  <div className="reaction-toggle-row">
                    <button
                      type="button"
                      className={`reaction-toggle-btn ${settingsParticipate ? "active" : ""}`}
                      onClick={() => setSettingsParticipate(true)}
                    >
                      Да
                    </button>
                    <button
                      type="button"
                      className={`reaction-toggle-btn ${!settingsParticipate ? "active" : ""}`}
                      onClick={() => setSettingsParticipate(false)}
                    >
                      Нет
                    </button>
                  </div>
                  {!showConfirmSave ? (
                    <div className="reaction-settings-actions">
                      <button
                        type="button"
                        className="reaction-settings-cancel"
                        onClick={() => {
                          setIsEditingSettings(false);
                          setShowConfirmSave(false);
                          setSettingsError("");
                        }}
                      >
                        Отмена
                      </button>
                      <button type="button" className="reaction-settings-save" disabled={!settingsChanged} onClick={() => setShowConfirmSave(true)}>
                        Продолжить
                      </button>
                    </div>
                  ) : (
                    <div className="reaction-confirm-box">
                      <div className="reaction-confirm-text">Подтвердить сохранение новых настроек участия?</div>
                      <div className="reaction-settings-actions">
                        <button type="button" className="reaction-settings-cancel" onClick={() => setShowConfirmSave(false)}>
                          Назад
                        </button>
                        <button
                          type="button"
                          className="reaction-settings-save"
                          disabled={isSavingSettings}
                          onClick={() => {
                            void saveLeaderboardSettings();
                          }}
                        >
                          {isSavingSettings ? "Сохраняем..." : "Подтвердить"}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
              {settingsSaved && <div className="reaction-settings-status">Настройки сохранены</div>}
              {settingsError && <div className="reaction-settings-error">{settingsError}</div>}
            </div>
          </section>
        </>
      )}

      {activeTab === "leaderboard" && (
        <section className="reaction-slide">
          <div className="reaction-leaderboard-card">
            <div className="reaction-leaderboard-header">
              <div className="reaction-leaderboard-title">Таблица лидеров</div>
              <div className="reaction-my-place">{myPlaceText}</div>
            </div>
            {leaderboardLoading ? (
              <div className="reaction-leaderboard-empty">Загрузка...</div>
            ) : leaderboardError ? (
              <div className="reaction-leaderboard-empty">{leaderboardError}</div>
            ) : leaderboard.entries.length === 0 ? (
              <div className="reaction-leaderboard-empty">Пока нет результатов для этой комбинации режима и сложности.</div>
            ) : (
              <div className="reaction-leaderboard-list">
                {leaderboard.entries.map((entry) => (
                  <div
                    key={`${entry.telegram_id}-${entry.mode}-${entry.difficulty}-${entry.score}-${entry.time_ms}`}
                    ref={entry.is_me ? meRowRef : null}
                    className={`reaction-row ${entry.is_me ? "is-me" : ""} ${entry.place <= 3 ? `top-${entry.place}` : ""}`}
                  >
                    <div className="reaction-row-place">
                      {entry.place === 1 ? "🥇" : entry.place === 2 ? "🥈" : entry.place === 3 ? "🥉" : `#${entry.place}`}
                    </div>
                    <div className="reaction-row-name-wrap">
                      <div className="reaction-row-name">{entry.name}</div>
                    </div>
                    <div className="reaction-row-time">
                      {mode === "timed" ? `${entry.score} очк` : `${formatSecondsMs(entry.time_ms)}с`}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      )}
    </>
  );
}

export default ReflexGridGamePage;
