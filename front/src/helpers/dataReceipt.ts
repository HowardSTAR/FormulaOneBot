/** Local presentation filters reuse the same calendar data, not a new receipt. */
export function dataReceiptKey(pathname: string, search: string): string {
  const params = new URLSearchParams(search);
  if (pathname === '/season') {
    params.delete('filter');
    params.delete('round');
  }
  params.sort();
  const query = params.toString();
  return pathname + (query ? `?${query}` : '');
}
