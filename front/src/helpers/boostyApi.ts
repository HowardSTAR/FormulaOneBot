import { apiRequest, ApiError } from './api';
import type { BoostyStatus } from './boosty';

export async function checkBoostySubscription(): Promise<BoostyStatus> {
  try {
    return await apiRequest<BoostyStatus>('/api/account/boosty/check', {}, 'POST', 120000);
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      // Read the retained status and safe failure category after an upstream failure.
      // Other server errors still use the normal API error handling.
      try {
        const status = await apiRequest<BoostyStatus>('/api/account/boosty');
        if (status.check_failed) return status;
      } catch { /* Preserve the original check error if status is also unavailable. */ }
    }
    throw error;
  }
}
