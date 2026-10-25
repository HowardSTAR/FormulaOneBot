export function homeTeamIdentity(id: string, name: string) {
  const value = `${id} ${name}`.toLowerCase().replace(/[^a-z]/g, '');
  return ['mclaren', 'mercedes', 'ferrari', 'redbull', 'williams', 'astonmartin', 'alpine', 'audi', 'cadillac', 'haas', 'racingbulls'].find(team => value.includes(team)) || 'unknown';
}
