export type JoystickDirection = { x: number; y: number };

// Screen and track share the same axes: right is +x, down is +y.
export function joystickDirection(dx: number, dy: number, radius: number): JoystickDirection | null {
  if (![dx, dy, radius].every(Number.isFinite) || radius <= 0) return null;
  const distance = Math.hypot(dx, dy);
  if (distance < radius * .12) return null;
  return { x: dx / distance, y: dy / distance };
}

export function aimJoystickHeading(heading: number, direction: JoystickDirection | null, delta: number): number {
  if (!direction || !Number.isFinite(delta) || delta <= 0) return heading;
  const target = Math.atan2(direction.y, direction.x);
  const difference = Math.atan2(Math.sin(target - heading), Math.cos(target - heading));
  const maximumTurn = 7 * delta;
  return heading + Math.max(-maximumTurn, Math.min(maximumTurn, difference));
}
