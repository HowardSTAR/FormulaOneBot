export type DriverOption = {
  code: string;
  name: string;
  constructorId?: string;
  constructorName?: string;
  is_favorite?: boolean;
};

export type CompareSeries = {
  code: string;
  history: number[];
  race_wins: number;
  quali_wins: number;
  total_points: number;
  average_points: number;
};

export type ColoredCompareSeries = CompareSeries & {
  color: string;
  name: string;
  teamName: string;
};

export const DRIVER_COLOR_PALETTE = [
  "#E10600",
  "#00D2BE",
  "#FF8700",
  "#64C4FF",
  "#FACC15",
  "#A855F7",
  "#22C55E",
  "#F43F5E",
  "#06B6D4",
  "#FB7185",
  "#8B5CF6",
  "#84CC16",
  "#F97316",
  "#14B8A6",
  "#EC4899",
  "#3B82F6",
  "#EAB308",
  "#10B981",
  "#C084FC",
  "#F87171",
  "#38BDF8",
  "#A3E635",
  "#F59E0B",
  "#2DD4BF",
] as const;

const TEAM_COLORS: Record<string, string> = {
  mclaren: "#FF8700",
  ferrari: "#E8002D",
  mercedes: "#00D2BE",
  redbull: "#3671C6",
  redbullracing: "#3671C6",
  astonmartin: "#229971",
  alpine: "#FF87BC",
  alpinef1team: "#FF87BC",
  williams: "#64C4FF",
  racingbulls: "#6692FF",
  rbf1team: "#6692FF",
  vcarb: "#6692FF",
  sauber: "#52E252",
  kicksauber: "#52E252",
  audi: "#F50537",
  haas: "#B6BABD",
  haasf1team: "#B6BABD",
  cadillac: "#C4A97D",
};

function normalizeTeamName(value?: string): string {
  return (value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function hexToRgb(hex: string): [number, number, number] {
  const normalized = hex.replace("#", "");
  return [
    Number.parseInt(normalized.slice(0, 2), 16),
    Number.parseInt(normalized.slice(2, 4), 16),
    Number.parseInt(normalized.slice(4, 6), 16),
  ];
}

function colorDistance(left: string, right: string): number {
  const [lr, lg, lb] = hexToRgb(left);
  const [rr, rg, rb] = hexToRgb(right);
  return Math.sqrt((lr - rr) ** 2 + (lg - rg) ** 2 + (lb - rb) ** 2);
}

function preferredTeamColor(driver: DriverOption): string | undefined {
  const normalized = normalizeTeamName(driver.constructorId || driver.constructorName);
  const exact = TEAM_COLORS[normalized];
  if (exact) return exact;
  const alias = Object.keys(TEAM_COLORS).find(
    (key) => normalized.includes(key) || key.includes(normalized)
  );
  return alias ? TEAM_COLORS[alias] : undefined;
}

export function assignDriverColors(drivers: DriverOption[]): Record<string, string> {
  const result: Record<string, string> = {};
  const used: string[] = [];

  drivers.forEach((driver, index) => {
    const preferred = preferredTeamColor(driver);
    const preferredIsDistinct =
      preferred && used.every((assigned) => colorDistance(preferred, assigned) >= 72);

    const fallback =
      DRIVER_COLOR_PALETTE.find(
        (candidate) =>
          !used.includes(candidate) &&
          used.every((assigned) => colorDistance(candidate, assigned) >= 72)
      ) ??
      DRIVER_COLOR_PALETTE.find((candidate) => !used.includes(candidate)) ??
      DRIVER_COLOR_PALETTE[index % DRIVER_COLOR_PALETTE.length];

    const color = preferredIsDistinct ? preferred : fallback;
    result[driver.code] = color;
    used.push(color);
  });

  return result;
}

export function rgbaFromHex(hex: string, alpha: number): string {
  const [red, green, blue] = hexToRgb(hex);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}
