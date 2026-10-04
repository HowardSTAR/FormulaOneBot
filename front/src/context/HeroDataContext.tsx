import { useState, useCallback, useRef, type ReactNode } from "react";
import { apiRequest } from "../helpers/api";
import { HeroDataContext } from "./heroDataContextObject";

export type NextRaceStatus = "ok" | "season_finished" | "error";

export type SessionItem = {
  name: string;
  utc_iso?: string;
  utc?: string;
};

export type NextRaceResponse = {
  status?: NextRaceStatus;
  event_name?: string;
  is_cancelled?: boolean;
  country?: string;
  location?: string;
  season?: number;
  round?: number;
  date?: string;
  fmt_date?: string;
  local?: string;
  race_start_utc?: string;
  next_session_iso?: string;
  next_session_name?: string;
};

type ScheduleResponse = { sessions?: SessionItem[] };
type SettingsResponse = { timezone?: string };

type HeroDataState = {
  nextRace: NextRaceResponse | null;
  schedule: SessionItem[];
  userTz: string;
  loaded: boolean;
};

export type HeroDataContextValue = HeroDataState & {
  load: () => Promise<void>;
};

const initialState: HeroDataState = {
  nextRace: null,
  schedule: [],
  userTz: "UTC",
  loaded: false,
};

export function HeroDataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<HeroDataState>(initialState);
  const pending = useRef<Promise<void> | null>(null);

  const load = useCallback(() => {
    if (pending.current) return pending.current;
    const request = (async () => {
      try {
        const [raceRes, settingsRes] = await Promise.allSettled([
          apiRequest<NextRaceResponse>("/api/next-race"),
          apiRequest<SettingsResponse>("/api/settings"),
        ]);

        const raceData = raceRes.status === "fulfilled" ? raceRes.value : { status: "error" as const };
        const settings = settingsRes.status === "fulfilled" ? settingsRes.value : { timezone: "UTC" };
        const tz = settings?.timezone || "UTC";

        setState({ nextRace: raceData, userTz: tz, schedule: [], loaded: false });

        if (raceData.status === "ok" && raceData.season && raceData.round) {
          try {
            const scheduleData = await apiRequest<ScheduleResponse>("/api/weekend-schedule", {
              season: raceData.season,
              round_number: raceData.round,
            });
            if (scheduleData?.sessions?.length) {
              setState((prev) => ({ ...prev, schedule: scheduleData.sessions! }));
            }
          } catch {
            // Fallback to next_session_iso/next_session_name from next-race
          }
        }
        setState(prev => ({ ...prev, loaded: true }));
      } catch (e) {
        console.error(e);
        setState((prev) => ({
          ...prev,
          nextRace: { status: "error", event_name: e instanceof Error ? e.message : "Ошибка" },
          loaded: true,
        }));
      }
    })().finally(() => { pending.current = null; });
    pending.current = request;
    return request;
  }, []);

  return (
    <HeroDataContext.Provider value={{ ...state, load }}>
      {children}
    </HeroDataContext.Provider>
  );
}
