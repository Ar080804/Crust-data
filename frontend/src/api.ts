// The ONLY file that knows whether data is mock or real.
// Components just call these functions.
import type { Request, Status, Expert, Eval } from '../../contract/types.ts'

import booked from '../../contract/fixtures/request_booked.json'
import negotiating from '../../contract/fixtures/request_negotiating.json'
import escalated from '../../contract/fixtures/request_escalated.json'
import clarify from '../../contract/fixtures/request_clarify.json'
import expertsFx from '../../contract/fixtures/experts.json'
import evalFx from '../../contract/fixtures/eval.json'

export const MOCK = import.meta.env.VITE_MOCK === 'true'
const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error((body as { error?: string }).error || `HTTP ${res.status}`)
  return body as T
}

// ---------------- mock layer ----------------
// Flows (pick by request text):
//   contains "escalate"     -> ESCALATED, Approve -> BOOKED
//   has no number in it     -> NEEDS_CLARIFICATION, answer -> NEGOTIATING -> BOOKED
//   anything else           -> NEGOTIATING for 5s, then BOOKED
const fx = <T,>(x: unknown) => structuredClone(x) as T
const mockState = new Map<string, { flow: 'demo' | 'clarify' | 'escalated'; since: number; resolved: boolean }>()
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function mockGet(id: string): Request {
  const s = mockState.get(id) ?? { flow: 'demo' as const, since: Date.now(), resolved: false }
  mockState.set(id, s)
  const elapsed = Date.now() - s.since
  let r: Request
  if (s.flow === 'clarify' && !s.resolved) r = fx<Request>(clarify)
  else if (s.flow === 'escalated' && !s.resolved) r = fx<Request>(escalated)
  else if (s.flow === 'escalated') r = fx<Request>(booked)
  else r = fx<Request>(elapsed < 5000 ? negotiating : booked)
  r.id = id
  return r
}

// ---------------- public API ----------------
export async function createRequest(text: string): Promise<{ request_id: string; status: Status }> {
  if (MOCK) {
    await sleep(300)
    const flow = /escalat/i.test(text) ? 'escalated' : /\d/.test(text) ? 'demo' : 'clarify'
    const id = `r_mock_${Date.now().toString(36)}`
    mockState.set(id, { flow, since: Date.now(), resolved: false })
    return { request_id: id, status: 'INTAKE' }
  }
  return http('/requests', { method: 'POST', body: JSON.stringify({ text }) })
}

export async function getRequest(id: string): Promise<Request> {
  if (MOCK) return mockGet(id)
  return http(`/requests/${encodeURIComponent(id)}`)
}

export async function sendClarification(id: string, answer: string): Promise<{ status: Status }> {
  if (MOCK) {
    const s = mockState.get(id)
    if (s) Object.assign(s, { resolved: true, flow: 'demo', since: Date.now() })
    return { status: 'NEGOTIATING' }
  }
  return http(`/requests/${encodeURIComponent(id)}/clarify`, { method: 'POST', body: JSON.stringify({ answer }) })
}

export async function approveOption(id: string, option_id: string): Promise<{ status: Status }> {
  if (MOCK) {
    const s = mockState.get(id)
    if (s) s.resolved = true
    return { status: 'BOOKED' }
  }
  return http(`/requests/${encodeURIComponent(id)}/approve`, { method: 'POST', body: JSON.stringify({ option_id }) })
}

export async function getExperts(): Promise<{ experts: Expert[] }> {
  if (MOCK) return fx(expertsFx)
  return http('/experts')
}

export async function getEval(): Promise<Eval> {
  if (MOCK) return fx(evalFx)
  return http('/eval/latest')
}
