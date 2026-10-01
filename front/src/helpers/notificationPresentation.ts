/** Old live-position payloads sometimes saved zero for every race points value. */
export function notificationBody(body: string, url: string): {body: string; uncertainPoints: boolean} {
  const rows = body.split('\n').filter(line => /^P\d+ · /.test(line));
  const uncertainPoints = /^\/(race|sprint)-results\?/.test(url) && rows.length >= 5 && rows.every(line => / · 0(?:\.0+)?$/.test(line.trim()));
  return {body: uncertainPoints ? body.replace(/( · )0(?:\.0+)?(?=\n|$)/g, '$1—') : body, uncertainPoints};
}
