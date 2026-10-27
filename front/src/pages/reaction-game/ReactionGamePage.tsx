import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GameLeaderboardPrompt } from "../../components/GameLeaderboardPrompt";
import { GlassSwitch } from "../index/GlassSwitch";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useAuthState } from "../../helpers/auth";
import { ApiError } from "../../helpers/api";
import { moveGameGlass, leaveGameGlass } from "../../helpers/gameGlassPointer";
import { GameExit } from "../../components/GameExit";
import { useGameLight } from "../../hooks/useGameLight";
import { usePageScrollLock } from "../../hooks/usePageScrollLock";
import { hapticImpact } from "../../helpers/telegram";
import { apiRequest } from "../../helpers/api";
import { ReactionDesktopScene } from "./ReactionDesktopScene";
import "../games.css";

type GameStatus = "idle" | "starting" | "armed" | "running" | "finished" | "false-start";

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

const MOBILE_LIGHT_COUNT = 4;
const DESKTOP_LIGHT_COUNT = 5;
const LAMPS_PER_LIGHT = 4;
const ACTIVE_LAMP_START_INDEX = 2;
const LIGHT_STEP_MS = 1000;
const RANDOM_DELAY_MIN_MS = 1000;
const RANDOM_DELAY_MAX_MS = 4000;

function getRandomStartDelayMs(): number {
  const range = RANDOM_DELAY_MAX_MS - RANDOM_DELAY_MIN_MS + 1;
  const cryptoApi = typeof window !== "undefined" ? window.crypto : undefined;
  if (cryptoApi?.getRandomValues) {
    const value = new Uint32Array(1);
    cryptoApi.getRandomValues(value);
    return RANDOM_DELAY_MIN_MS + Math.floor((value[0] / 2 ** 32) * range);
  }
  return RANDOM_DELAY_MIN_MS + Math.floor(Math.random() * range);
}

function formatSecondsMs(ms: number): string {
  return (ms / 1000).toFixed(3);
}

function ReactionGamePage() {
  const [status, setStatus] = useState<GameStatus>("idle");
  const auth = useAuthState();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") === "leaderboard" ? "leaderboard" : "game";
  const tabItems = ["game", "leaderboard"].map(id => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", id);
    return { id, label: id === "game" ? "Игра" : "Лидеры", to: `${location.pathname}?${params}` };
  });
  const [activeLights, setActiveLights] = useState(0);
  const [sequenceLightCount, setSequenceLightCount] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(min-width: 900px)").matches
      ? DESKTOP_LIGHT_COUNT
      : MOBILE_LIGHT_COUNT
  );
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
  const scrollLocked = status === "starting" || status === "armed" || status === "running";

  usePageScrollLock(scrollLocked);
  const playSurface = useRef<HTMLDivElement>(null);
  useGameLight(playSurface, ".reaction-button, .reaction-desktop-start", activeTab);

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
          apiRequest<LeaderboardProfile>("/api/reaction-leaderboard/profile").catch(error => {
            if (error instanceof ApiError && error.status === 401) return { display_name: "", participate: false, prompt_seen: true };
            throw error;
          }),
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
    const lightCount = window.matchMedia("(min-width: 900px)").matches
      ? DESKTOP_LIGHT_COUNT
      : MOBILE_LIGHT_COUNT;
    setStatus("starting");
    setActiveLights(0);
    setSequenceLightCount(lightCount);
    setCurrentTimeMs(0);
    setResultTimeMs(null);
    timerStartRef.current = null;

    for (let index = 1; index <= lightCount; index += 1) {
      const timeoutId = window.setTimeout(() => {
        setActiveLights(index);
      }, index * LIGHT_STEP_MS);
      timeoutIdsRef.current.push(timeoutId);
    }

    const totalStartMs = lightCount * LIGHT_STEP_MS;
    // После включения всех огней старт назначается заново для каждой попытки.
    // Криптографический источник не повторяет предсказуемую последовательность
    const randomDelayMs = getRandomStartDelayMs();

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
    playSurface.current?.scrollIntoView({ block: "start", behavior: "instant" });
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

  const handleMainAction = useCallback(() => {
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
  }, [falseStart, startGame, status, stopGameTimer]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Space") return;
      if (event.repeat || activeTab !== "game" || showOnboarding) return;
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable || target?.closest("input, textarea, select, button, a, dialog")) return;
      event.preventDefault();
      handleMainAction();
    };

    window.addEventListener("keydown", onKeyDown, { passive: false });
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeTab, handleMainAction, showOnboarding]);

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
      ? "Стоп"
      : status === "starting" || status === "armed"
        ? "Жди"
        : status === "idle"
          ? "Старт"
          : status === "false-start"
            ? "Новая попытка"
            : "Сыграть ещё раз";

  const myPlaceText = useMemo(() => {
    if (!leaderboard.me) return "Пока нет результата в таблице";
    return `Твое место: #${leaderboard.me.place} (${formatSecondsMs(leaderboard.me.time_ms)} сек)`;
  }, [leaderboard.me]);
  const settingsChanged =
    settingsName.trim() !== (profile.display_name || "").trim() || settingsParticipate !== profile.participate;

  return (
    <div className="game-page reaction-game-page" onPointerMove={moveGameGlass} onPointerDown={moveGameGlass} onPointerLeave={leaveGameGlass} onPointerUp={leaveGameGlass} onPointerCancel={leaveGameGlass}>
      {showOnboarding && <GameLeaderboardPrompt
        name={settingsName} participate={settingsParticipate} saving={isSavingSettings} error={settingsError}
        onNameChange={setSettingsName} onParticipateChange={setSettingsParticipate}
        onContinue={() => { if (!isSavingSettings) void saveLeaderboardSettings({ fromOnboarding: true }); }}
        onDismiss={() => { setShowOnboarding(false); setSettingsError(""); setSettingsName(profile.display_name); setSettingsParticipate(profile.participate); }}
      />}

      <GameExit playing={scrollLocked} />
      <h1>Тест реакции</h1>
      <p className="reaction-subtitle">Стартовые огни загораются по очереди и гаснут в случайный момент.</p>
      <GlassSwitch items={tabItems} selected={activeTab} label="Игра и таблица лидеров" className="game-view-switch" replace />

      {activeTab === "game" && (
        <>
          <div ref={playSurface} className="game-play-surface reaction-play-surface" data-state={status}>
          <div className="reaction-mobile-scene">
          <div className="reaction-board" aria-label="Стартовые огни Formula 1">
            {Array.from({ length: MOBILE_LIGHT_COUNT }).map((_, lightIndex) => {
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

          <div className="reaction-timer-card" data-state={status}>
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
            data-analytics-action={status === 'running' || status === 'starting' || status === 'armed' ? 'game_hit' : 'game_start'} onClick={handleMainAction}
          >
            {buttonLabel}
          </button>
          <p className="reaction-helper" role="status">{helperText}</p>
          </div>
          <ReactionDesktopScene
            status={status}
            activeLights={activeLights}
            totalLights={sequenceLightCount}
            currentTimeMs={currentTimeMs}
            resultTimeMs={resultTimeMs}
            bestTimeMs={bestTimeMs}
            onAction={handleMainAction}
          />
          </div>

          <section className="reaction-slide">
            <div className="reaction-settings-card">
              <div className="reaction-settings-title">Участие в лидерборде</div>
              {!auth.signedIn ? <p className="reaction-settings-caption"><Link to="/account">Войдите</Link>, чтобы настроить имя и участие в рейтинге.</p> : !isEditingSettings ? (
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
                    aria-label="Имя в таблице" name="display_name" autoComplete="nickname"
                    placeholder="Имя в таблице"
                    value={settingsName}
                    onChange={(e) => setSettingsName(e.target.value)}
                    maxLength={32}
                  />
                  <div className="reaction-toggle-row">
                    <button
                      type="button"
                      aria-pressed={settingsParticipate}
                      className={`reaction-toggle-btn ${settingsParticipate ? "active" : ""}`}
                      onClick={() => setSettingsParticipate(true)}
                    >
                      Да
                    </button>
                    <button
                      type="button"
                      aria-pressed={!settingsParticipate}
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
                          {isSavingSettings ? "Сохраняем…" : "Подтвердить"}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
              {settingsSaved && <div role="status" className="reaction-settings-status">Настройки сохранены</div>}
              {settingsError && <div role="alert" className="reaction-settings-error">{settingsError}</div>}
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
                <div className="reaction-leaderboard-empty">Загрузка…</div>
              ) : leaderboardError ? (
                <div role="alert" className="reaction-leaderboard-empty">{leaderboardError}<button type="button" className="reaction-settings-edit" onClick={() => void fetchLeaderboard()}>Повторить загрузку</button></div>
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
                        #{entry.place}
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
    </div>
  );
}

export default ReactionGamePage;
