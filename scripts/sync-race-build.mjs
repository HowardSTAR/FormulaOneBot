import { cp } from 'node:fs/promises'

// Copy only generated assets; retain old hashed bundles for already open tabs.
await cp(new URL('../race-game/dist/', import.meta.url), new URL('../front/public/race-game/', import.meta.url), { recursive: true })
