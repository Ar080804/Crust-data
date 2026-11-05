// FRONTEND-ONLY auth draft. The backend has no auth endpoints yet (see contract/CONTRACT.md),
// so the "account" lives only in this browser. Swap these functions for real API calls later.
import { useEffect, useState } from 'react'

export interface User { name: string; email: string; provider: 'email' | 'google' | 'guest' }
const KEY = 'sutradhar_user'
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
