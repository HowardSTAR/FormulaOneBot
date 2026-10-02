export const NOTIFY_OPTIONS = [
  { value: 15, label: "15 минут" },
  { value: 30, label: "30 минут" },
  { value: 60, label: "1 час" },
  { value: 120, label: "2 часа" },
  { value: 1440, label: "24 часа" },
];

export function selectedIntervals(values?: number[], legacy = 60): number[] {
  // An empty selection disables reminders. Only an absent field uses the legacy value.
  if (values === undefined) return [legacy];
  return NOTIFY_OPTIONS.filter(({value}) => values.includes(value)).map(({value}) => value);
}

export function toggleInterval(current: number[], minutes: number): number[] {
  return selectedIntervals(current.includes(minutes) ? current.filter(value => value !== minutes) : [...current, minutes]);
}
