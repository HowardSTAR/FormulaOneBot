/** Local UI estimate only. The server remains the authority for password policy.
 * Nothing in this module stores, logs or transmits the input.
 */
export type PasswordStrengthLevel = 0 | 1 | 2 | 3 | 4;
export type RacerPhase = 'idle' | 'start' | 'accelerate_1' | 'accelerate_2' | 'accelerate_3' | 'max_speed';

const common = /password|qwerty|asdfgh|zxcvbn|letmein|iloveyou|admin|пароль|turbotears|formulaone/i;

export function estimatePasswordStrength(password: string): PasswordStrengthLevel {
  const chars = [...password];
  if (!chars.length) return 0;
  const compact = password.toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
  const unique = new Set(compact).size;
  if (unique < 4 || common.test(compact) || /^(?:0123456789|1234567890|9876543210|123456789|987654321)+\d*$/.test(compact)
    || /^(.{1,6})\1+$/u.test(password)) return 1;
  if (chars.length < 10) return 1;
  if (chars.length < 15) return 2;
  // Long phrases in any language are welcome; symbol classes aren't mandatory.
  if (chars.length > 128 || /[\p{Cc}\p{Cs}]/u.test(password)) return 2;
  if (chars.length < 20 || unique < 9) return 3;
  return 4;
}

export const speedTargets = [0, .18, .43, .72, 1] as const;

/** Start is a short ignition transition. The five scores then map to five steady states. */
export function racerPhase(level: PasswordStrengthLevel, starting: boolean): RacerPhase {
  if (level === 0) return 'idle';
  if (starting) return 'start';
  return (['idle', 'accelerate_1', 'accelerate_2', 'accelerate_3', 'max_speed'] as const)[level];
}

export function damp(current: number, target: number, rate: number, delta: number): number {
  return current + (target - current) * (1 - Math.exp(-rate * delta));
}
