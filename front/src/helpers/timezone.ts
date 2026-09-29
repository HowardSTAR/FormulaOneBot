export function getDisplayTimezone(savedTimezone?: string): string {
  if (savedTimezone && savedTimezone !== "UTC") {
    return savedTimezone;
  }
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** Human-facing label; keep the IANA identifier for Intl formatting. */
export function formatTimezoneLabel(timezone: string): string {
  if (timezone === "Europe/Moscow" || timezone === "Etc/GMT-3") return "МСК (UTC+3)";
  if (timezone === "UTC" || timezone === "Etc/UTC") return "UTC";
  const fixed = /^Etc\/GMT([+-])(\d{1,2})$/.exec(timezone);
  if (fixed) return `UTC${fixed[1] === "+" ? "−" : "+"}${fixed[2]}`;
  return timezone.replace(/_/g, " ");
}
