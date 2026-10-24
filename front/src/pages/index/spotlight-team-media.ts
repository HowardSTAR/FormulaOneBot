// 2026 media verified against https://www.formula1.com/en/teams.
// Other seasons continue to use the project's season-aware asset endpoints.
const currentTeams = ['alpine', 'astonmartin', 'audi', 'cadillac', 'ferrari', 'haasf1team', 'mclaren', 'mercedes', 'racingbulls', 'redbullracing', 'williams'];
const aliases: Record<string, string> = { haas: 'haasf1team', redbull: 'redbullracing', rb: 'racingbulls', rbf1team: 'racingbulls', alpinef1team: 'alpine', astonmartinf1team: 'astonmartin' };
export function spotlightTeamMedia(id: string, name: string, season: number) {
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '');
  const identity = normalize(id || name);
  const slug = aliases[identity] || currentTeams.find(team => identity === team || normalize(name).includes(team));
  const cdn = 'https://media.formula1.com/image/upload';
  const path = `v1740000001/common/f1/2026/${slug}/2026${slug}`;
  return {
    logo: season === 2026 && slug ? [`${cdn}/c_fit,w_480/q_auto/${path}logowhite.webp`] : [],
    car: season === 2026 && slug ? [`${cdn}/c_fit,w_1400/q_auto/${path}carright.webp`] : [],
  };
}
