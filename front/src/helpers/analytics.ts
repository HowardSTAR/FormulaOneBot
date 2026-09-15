import { apiRequest } from './api';
import { hasTelegramAuth } from './auth';

export function analyticsPlatform() {
  if (hasTelegramAuth()) return 'telegram';
  if (window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone) return 'pwa';
  return 'browser';
}

export function trackPrediction(event: 'prediction_view' | 'prediction_start', season: number, round: number) {
  void apiRequest('/api/analytics/event', { event, path: '/predictions', season, round, platform: analyticsPlatform() }, 'POST').catch(() => {});
}
