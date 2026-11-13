// Remembers which requests this browser created (per signed-in user).
// Needed because the contract has no "list my requests" endpoint yet. Once the backend adds
// GET /requests, api.listMyRequests() can switch to it and this file becomes a cache.
import { getUser } from './auth.ts'

export interface Saved { id: string; text: string; created_at: string }

function accountKey() {
  const user = getUser()
  if (user?.provider === 'linkedin' && user.subject) return `linkedin:${user.subject}`
  return user?.email || 'guest'
}
const key = () => `sutradhar_requests:${accountKey()}`
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

/* ---- chat messages with experts, per request ---- */
export interface ChatMsg { id: string; expert_id: string; from: 'me' | 'expert'; text: string; t: string }
const chatKey = (rid: string) => `sutradhar_chat:${accountKey()}:${rid}`
const chatMem: Record<string, ChatMsg[]> = {}

export function listChat(rid: string): ChatMsg[] {
  try {
    const s = localStorage.getItem(chatKey(rid))
    return s ? (JSON.parse(s) as ChatMsg[]) : (chatMem[chatKey(rid)] ?? [])
  } catch { return chatMem[chatKey(rid)] ?? [] }
}

export function addChat(rid: string, m: Omit<ChatMsg, 'id' | 't'>): ChatMsg {
  const msg: ChatMsg = { ...m, id: Math.random().toString(36).slice(2), t: new Date().toISOString() }
  const list = [...listChat(rid), msg]
  chatMem[chatKey(rid)] = list
  try { localStorage.setItem(chatKey(rid), JSON.stringify(list)) } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent('sutradhar-chat', { detail: rid }))
  return msg
}
