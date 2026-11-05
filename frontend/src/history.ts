// Remembers which requests this browser created (per signed-in user).
// Needed because the contract has no "list my requests" endpoint yet. Once the backend adds
// GET /requests, api.listMyRequests() can switch to it and this file becomes a cache.
import { getUser } from './auth.ts'

export interface Saved { id: string; text: string; created_at: string }

const key = () => `sutradhar_requests:${getUser()?.email || 'guest'}`
const mem: Record<string, Saved[]> = {}

export function listSaved(): Saved[] {
  try {
    const s = localStorage.getItem(key())
    return s ? (JSON.parse(s) as Saved[]) : (mem[key()] ?? [])
  } catch { return mem[key()] ?? [] }
}

function write(list: Saved[]) {
  mem[key()] = list
  try { localStorage.setItem(key(), JSON.stringify(list)) } catch { /* ignore */ }
}

export function saveRequest(s: Saved) {
  write([s, ...listSaved().filter((x) => x.id !== s.id)].slice(0, 50))
}

export function removeSaved(id: string) {
  write(listSaved().filter((x) => x.id !== id))
}
