import { useEffect, useState } from 'react'

export interface User { name: string; email: string | null; provider: 'email' | 'google' | 'linkedin' | 'guest'; subject?: string | null; picture?: string }
const KEY = 'sutradhar_user'
const TOKEN_KEY = 'sutradhar_session' // Provider session issued by the backend

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
}
let memory: User | null = null // fallback when localStorage is blocked

export function getUser(): User | null {
  try {
    const s = localStorage.getItem(KEY)
    return s ? (JSON.parse(s) as User) : memory
  } catch { return memory }
}

export function signIn(u: User) {
  memory = u
  try { localStorage.setItem(KEY, JSON.stringify(u)) } catch { /* ignore */ }
  window.dispatchEvent(new Event('sutradhar-auth'))
}

export function signOut() {
  memory = null
  setToken(null)
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
  window.dispatchEvent(new Event('sutradhar-auth'))
}

export function useUser() {
  const [u, setU] = useState<User | null>(getUser)
  useEffect(() => {
    const f = () => setU(getUser())
    window.addEventListener('sutradhar-auth', f)
    return () => window.removeEventListener('sutradhar-auth', f)
  }, [])
  return u
}

export const nameFromEmail = (email: string) =>
  email.split('@')[0].replace(/[._-]+/g, ' ').replace(/\d+/g, '').trim().replace(/\b\w/g, (c) => c.toUpperCase()) || 'Friend'
