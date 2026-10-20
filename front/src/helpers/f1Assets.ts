import { apiAssetUrl } from './api';

export function pilotPortraitUrl(code: string, fullName: string, season: number): string {
  return apiAssetUrl('/api/pilot-portrait', { season, code, name: fullName });
}

export function teamLogoUrl(teamId: string, teamName: string, season: number): string {
  return apiAssetUrl('/api/team-logo', { team: teamId || teamName, name: teamName, season });
}

export function carImageUrl(teamName: string, season: number): string {
  return apiAssetUrl('/api/car-image', { team: teamName, season });
}
