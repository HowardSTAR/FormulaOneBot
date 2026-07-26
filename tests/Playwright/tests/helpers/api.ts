import { APIRequestContext, expect } from "@playwright/test";

export type NextRace = {
  status: string;
  season: number;
  round: number;
  event_name: string;
  is_cancelled: boolean;
  country: string;
  location: string;
  date: string;
  race_start_utc?: string | null;
};

export type SeasonRace = {
  round: number;
  event_name: string;
  country: string;
  location: string;
  date: string;
  is_cancelled: boolean;
};

/** Resolve a stable season for assertions (next-race → current year). */
export async function resolveSeason(request: APIRequestContext): Promise<number> {
  const next = await request.get("/api/next-race");
  if (next.ok()) {
    const body = (await next.json()) as Partial<NextRace>;
    if (typeof body.season === "number") return body.season;
  }
  return new Date().getUTCFullYear();
}

export async function getNextRace(
  request: APIRequestContext,
  season?: number
): Promise<NextRace> {
  const response = await request.get("/api/next-race", {
    params: season != null ? { season: String(season) } : undefined,
  });
  expect(response.ok(), `next-race status ${response.status()}`).toBeTruthy();
  return (await response.json()) as NextRace;
}

export async function getJson<T>(
  request: APIRequestContext,
  path: string,
  params?: Record<string, string | number | boolean>
): Promise<{ status: number; body: T }> {
  const response = await request.get(path, {
    params: params
      ? Object.fromEntries(
          Object.entries(params).map(([k, v]) => [k, String(v)])
        )
      : undefined,
  });
  const body = (await response.json()) as T;
  return { status: response.status(), body };
}

export function expectSortedByPosition<T extends { position: number }>(
  items: T[]
): void {
  for (let i = 1; i < items.length; i++) {
    expect(
      items[i].position,
      `position order broken at index ${i}`
    ).toBeGreaterThanOrEqual(items[i - 1].position);
  }
}
