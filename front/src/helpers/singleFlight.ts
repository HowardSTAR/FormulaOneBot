/** Share only simultaneous reads, never cache fulfilled data or failed reads. */
export class SingleFlight {
  private pending = new Map<string, Promise<unknown>>();

  clear(): void {
    // Invalidate sharing after an identity change; callers already awaiting a
    // request still receive its result, but it cannot replace a newer flight.
    this.pending.clear();
  }

  run<T>(key: string, request: () => Promise<T>): Promise<T> {
    const existing = this.pending.get(key);
    if (existing) return existing as Promise<T>;
    const promise = Promise.resolve().then(request).finally(() => {
      if (this.pending.get(key) === promise) this.pending.delete(key);
    });
    this.pending.set(key, promise);
    return promise;
  }
}
