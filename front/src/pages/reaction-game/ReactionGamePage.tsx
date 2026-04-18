import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BackButton } from "../../components/BackButton";
import { hapticImpact, hapticSelection } from "../../helpers/telegram";
import { apiRequest } from "../../helpers/api";

type GameStatus = "idle" | "starting" | "armed" | "running" | "finished" | "false-start";
type ReactionTab = "game" | "leaderboard";

type LeaderboardProfile = {
  display_name: string;
  participate: boolean;
  prompt_seen: boolean;
};

type LeaderboardEntry = {
  place: number;
  telegram_id: number;
  name: string;
  time_ms: number;
  is_me: boolean;
};

type LeaderboardResponse = {
  entries: LeaderboardEntry[];
  me: LeaderboardEntry | null;
};

const LIGHT_COUNT = 4;
const LAMPS_PER_LIGHT = 4;
const ACTIVE_LAMP_START_INDEX = 2;
const LIGHT_STEP_MS = 1500;
const RANDOM_DELAY_MIN_MS = 1200;
const RANDOM_DELAY_MAX_MS = 3200;

function formatSecondsMs(ms: number): string {
  return (ms / 1000).toFixed(3);
}

function ReactionGamePage() {
  const [status, setStatus] = useState<GameStatus>("idle");
  const [activeTab, setActiveTab] = useState<ReactionTab>("game");
  const [activeLights, setActiveLights] = useState(0);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [resultTimeMs, setResultTimeMs] = useState<number | null>(null);
  const [bestTimeMs, setBestTimeMs] = useState<number | null>(null);
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
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse>({ entries: [], me: null });
  const [leaderboardLoading, setLeaderboardLoading] = useState(true);
  const [leaderboardError, setLeaderboardError] = useState("");
  const meRowRef = useRef<HTMLDivElement | null>(null);

  const rafIdRef = useRef<number | null>(null);
  const timerStartRef = useRef<number | null>(null);
  const timeoutIdsRef = useRef<number[]>([]);

  const clearAllTimers = useCallback(() => {
    timeoutIdsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    timeoutIdsRef.current = [];
    if (rafIdRef.current != null) {
      window.cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  useEffect(() => clearAllTimers, [clearAllTimers]);

  const fetchLeaderboard = useCallback(async () => {
    try {
      setLeaderboardLoading(true);
      setLeaderboardError("");
      const data = await apiRequest<LeaderboardResponse>("/api/reaction-leaderboard");
      setLeaderboard(data);
    } catch (e) {
      setLeaderboardError(e instanceof Error ? e.message : "Не удалось загрузить таблицу лидеров");
    } finally {
      setLeaderboardLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [profileData, leaderboardData] = await Promise.all([
          apiRequest<LeaderboardProfile>("/api/reaction-leaderboard/profile"),
          apiRequest<LeaderboardResponse>("/api/reaction-leaderboard"),
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
  }, []);

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

  const submitResultToLeaderboard = useCallback(
    async (timeMs: number) => {
      if (!profile.participate) return;
      try {
        await apiRequest("/api/reaction-leaderboard/score", { time_ms: Math.max(1, Math.round(timeMs)) }, "POST");
        await fetchLeaderboard();
      } catch (e) {
        console.warn("Reaction leaderboard submit failed", e);
      }
    },
    [fetchLeaderboard, profile.participate]
  );

  const startRunTimer = useCallback(() => {
    timerStartRef.current = performance.now();
    setCurrentTimeMs(0);
    setStatus("running");

    const tick = () => {
      if (timerStartRef.current == null) return;
      setCurrentTimeMs(performance.now() - timerStartRef.current);
      rafIdRef.current = window.requestAnimationFrame(tick);
    };

    rafIdRef.current = window.requestAnimationFrame(tick);
  }, []);

  const scheduleLightSequence = useCallback(() => {
    setStatus("starting");
    setActiveLights(0);
    setCurrentTimeMs(0);
    setResultTimeMs(null);
    timerStartRef.current = null;

    for (let index = 1; index <= LIGHT_COUNT; index += 1) {
      const timeoutId = window.setTimeout(() => {
        setActiveLights(index);
      }, index * LIGHT_STEP_MS);
      timeoutIdsRef.current.push(timeoutId);
    }

    const totalStartMs = LIGHT_COUNT * LIGHT_STEP_MS;
    const randomDelayMs =
      RANDOM_DELAY_MIN_MS + Math.floor(Math.random() * (RANDOM_DELAY_MAX_MS - RANDOM_DELAY_MIN_MS + 1));

    const armId = window.setTimeout(() => {
      setStatus("armed");
    }, totalStartMs);
    timeoutIdsRef.current.push(armId);

    const startTimerId = window.setTimeout(() => {
      setActiveLights(0);
      startRunTimer();
    }, totalStartMs + randomDelayMs);
    timeoutIdsRef.current.push(startTimerId);
  }, [startRunTimer]);

  const startGame = useCallback(() => {
    clearAllTimers();
    scheduleLightSequence();
  }, [clearAllTimers, scheduleLightSequence]);

  const stopGameTimer = useCallback(() => {
    if (rafIdRef.current != null) {
      window.cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    if (timerStartRef.current == null) return;

    const finalMs = performance.now() - timerStartRef.current;
    setCurrentTimeMs(finalMs);
    setResultTimeMs(finalMs);
    setBestTimeMs((prev) => (prev == null ? finalMs : Math.min(prev, finalMs)));
    timerStartRef.current = null;
    setStatus("finished");
    void submitResultToLeaderboard(finalMs);
  }, [submitResultToLeaderboard]);

  const falseStart = useCallback(() => {
    clearAllTimers();
    setStatus("false-start");
    setActiveLights(0);
    setCurrentTimeMs(0);
    setResultTimeMs(null);
    timerStartRef.current = null;
  }, [clearAllTimers]);

  const handleMainAction = () => {
    if (status === "running") {
      hapticImpact("medium");
      stopGameTimer();
      return;
    }

    if (status === "starting" || status === "armed") {
      hapticImpact("heavy");
      falseStart();
      return;
    }

    hapticImpact("light");
    startGame();
  };

  const helperText =
    status === "running"
      ? "Жми кнопку как можно быстрее"
      : status === "starting" || status === "armed"
        ? "Ждать! Нажатие сейчас считается фальстартом"
        : status === "false-start"
          ? "Фальстарт. Нажми «Новая попытка»"
          : "Нажми «Старт» и жди, пока огни погаснут";

  const buttonLabel =
    status === "running"
      ? "СТОП"
      : status === "starting" || status === "armed"
        ? "ЖДИ"
        : status === "idle"
          ? "СТАРТ"
          : "ЕЩЕ РАЗ";

  const myPlaceText = useMemo(() => {
    if (!leaderboard.me) return "Пока нет результата в таблице";
    return `Твое место: #${leaderboard.me.place} (${formatSecondsMs(leaderboard.me.time_ms)} сек)`;
  }, [leaderboard.me]);
  const settingsChanged =
    settingsName.trim() !== (profile.display_name || "").trim() || settingsParticipate !== profile.participate;

  return (
    <>
      {showOnboarding && (
        <div className="reaction-modal-overlay">
          <div className="reaction-modal-card">
            <h3 className="reaction-modal-title">Таблица лидеров</h3>
            <p className="reaction-modal-text">Хочешь участвовать в рейтинге реакции?</p>
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

      <BackButton>← <span>На главную</span></BackButton>
      <h2 style={{ marginTop: 10, marginBottom: 10 }}>Тест реакции</h2>
      <p className="reaction-subtitle">4 светофора запускаются слева направо, отпускают в случайный момент.</p>
      <div className="segmented-tabs reaction-segmented">
        <div
          className="segmented-slider"
          style={{ transform: activeTab === "game" ? "translateX(0)" : "translateX(100%)" }}
          aria-hidden
        />
        <button
          type="button"
          className={`segmented-tab ${activeTab === "game" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setActiveTab("game");
          }}
        >
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

      {activeTab === "game" && (
        <>
          <div className="reaction-board">
            {Array.from({ length: LIGHT_COUNT }).map((_, lightIndex) => {
              const isActive = lightIndex < activeLights;
              return (
                <div key={lightIndex} className={`reaction-light ${isActive ? "active" : ""}`}>
                  {Array.from({ length: LAMPS_PER_LIGHT }).map((__, lampIndex) => (
                    <span
                      key={`${lightIndex}-${lampIndex}`}
                      className={`reaction-lamp ${lampIndex >= ACTIVE_LAMP_START_INDEX ? "is-bottom" : ""}`}
                    />
                  ))}
                </div>
              );
            })}
          </div>

          <div className="reaction-timer-card">
            <div className="reaction-main-time">{formatSecondsMs(currentTimeMs)}</div>
            <div className="reaction-time-unit">сек</div>
            {resultTimeMs != null && (
              <div className="reaction-result">Твоя реакция: {formatSecondsMs(resultTimeMs)} сек</div>
            )}
            {bestTimeMs != null && <div className="reaction-best">Лучший результат: {formatSecondsMs(bestTimeMs)} сек</div>}
          </div>

          <button
            type="button"
            className={`reaction-button ${status === "running" ? "is-stop" : ""}`}
            onClick={handleMainAction}
          >
            {buttonLabel}
          </button>
          <p className="reaction-helper">{helperText}</p>

          <section className="reaction-slide">
            <div className="reaction-settings-card">
              <div className="reaction-settings-title">Участие в лидерборде</div>
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
                  <p className="reaction-settings-caption">
                    Режим редактирования. Изменения применятся только после подтверждения.
                  </p>
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
                      <button
                        type="button"
                        className="reaction-settings-save"
                        disabled={!settingsChanged}
                        onClick={() => setShowConfirmSave(true)}
                      >
                        Продолжить
                      </button>
                    </div>
                  ) : (
                    <div className="reaction-confirm-box">
                      <div className="reaction-confirm-text">Подтвердить сохранение новых настроек участия?</div>
                      <div className="reaction-settings-actions">
                        <button
                          type="button"
                          className="reaction-settings-cancel"
                          onClick={() => setShowConfirmSave(false)}
                        >
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
                <div className="reaction-leaderboard-empty">Пока нет результатов. Стань первым!</div>
              ) : (
                <div className="reaction-leaderboard-list">
                  {leaderboard.entries.map((entry) => (
                    <div
                      key={`${entry.telegram_id}-${entry.time_ms}`}
                      ref={entry.is_me ? meRowRef : null}
                      className={`reaction-row ${entry.is_me ? "is-me" : ""} ${
                        entry.place <= 3 ? `top-${entry.place}` : ""
                      }`}
                    >
                      <div className="reaction-row-place">
                        {entry.place === 1 ? "🥇" : entry.place === 2 ? "🥈" : entry.place === 3 ? "🥉" : `#${entry.place}`}
                      </div>
                      <div className="reaction-row-name-wrap">
                        <div className="reaction-row-name">{entry.name}</div>
                        {entry.place === 1 && <div className="reaction-world-champion">World Champion</div>}
                      </div>
                      <div className="reaction-row-time">{formatSecondsMs(entry.time_ms)}</div>
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

export default ReactionGamePage;
