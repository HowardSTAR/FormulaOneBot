export function getDisplayTimezone(savedTimezone?: string): string {
  if (savedTimezone && savedTimezone !== "UTC") {
    return savedTimezone;
  }
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}
