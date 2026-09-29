/** The Grand Prix title can differ from its actual host circuit. */
export function resolveCircuitAsset(eventName: string, location?: string, season?: number): string {
  if (season === 2026 && /bahrain/i.test(eventName) && /sepang|kuala lumpur|malaysia/i.test(location || "")) {
    return "Sepang Grand Prix";
  }
  return eventName;
}
