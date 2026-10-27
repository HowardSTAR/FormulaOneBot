const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });
export function entrantValue(value: string | number | null | undefined) {
  return typeof value === 'number' ? numberFormat.format(value) : value || '—';
}
