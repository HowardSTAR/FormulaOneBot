// Local synthetic classifications match the Jolpica MRData shape consumed by
// prediction_history and prediction_analytics. No real driver data or credentials.
const http = require('http');
let failing = true;
const drivers = Array.from({ length: 20 }, (_, i) => ({
  driverId: `fixture${i}`, code: `D${i}`, givenName: 'Fixture', familyName: `Driver ${i}`,
}));
http.createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  const answer = (status, body) => {
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(body));
  };
  if (path === '/control/fail') { failing = true; return answer(200, {}); }
  if (path === '/control/recover') { failing = false; return answer(200, {}); }
  if (failing) return answer(503, { error: 'synthetic provider outage' });
  if (/\/drivers\/?$/.test(path)) return answer(200, { MRData: { DriverTable: { Drivers: drivers } } });
  const match = path.match(/^\/(\d{4})\/(results|qualifying)\/?$/);
  if (!match) return answer(501, { error: 'Endpoint outside this fixture contract' });
  const year = Number(match[1]);
  const field = match[2] === 'results' ? 'Results' : 'QualifyingResults';
  const races = [1, 2, 3].map(round => ({
    season: String(year), round: String(round), date: `${year}-01-0${round}`, time: '12:00:00Z',
    raceName: `Fixture ${round}`, Circuit: { circuitId: 'fixture', Location: { locality: 'Fixture' } },
    [field]: drivers.map((Driver, i) => ({ position: String(i+1), grid: String(i+1),
      Driver, Constructor: { name: `Team ${Math.floor(i/2)}`, constructorId: `team${Math.floor(i/2)}` }, status: 'Finished' })),
  }));
  answer(200, { MRData: { total: '60', RaceTable: { Races: races } } });
}).listen(process.env.PORT || 4900);
