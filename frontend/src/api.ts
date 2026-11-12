// The ONLY file that knows whether data is mock or real.
// Components just call these functions.
import { getToken } from './auth.ts'
import type { Request, Status, Expert, Eval, AuthUser } from '../../contract/types.ts'

import booked from '../../contract/fixtures/request_booked.json'
import negotiating from '../../contract/fixtures/request_negotiating.json'
import escalated from '../../contract/fixtures/request_escalated.json'
import clarify from '../../contract/fixtures/request_clarify.json'
import expertsFx from '../../contract/fixtures/experts.json'
import evalFx from '../../contract/fixtures/eval.json'
import { addChat, listChat, listSaved, removeSaved, saveRequest, type ChatMsg, type Saved } from './history.ts'

export const MOCK = import.meta.env.VITE_MOCK === 'true'
// Sunil's expert onboarding server (real LinkedIn OIDC). Experts join there; clients never log in with LinkedIn.
export const ONBOARDING_URL: string = import.meta.env.VITE_ONBOARDING_URL || (import.meta.env.DEV ? 'http://localhost:8001' : '')
const BASE = (import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '/api')).replace(/\/$/, '')

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(BASE + path, { ...init, headers })
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
//   time window outside 5–10 PM -> ESCALATED with no options ("no expert free"), like the real backend
type Flow = 'demo' | 'clarify' | 'escalated' | 'unavailable'
const mockState = new Map<string, { flow: Flow; since: number; resolved: boolean }>()
const MOCK_FREE = [17, 22] // pool_example availability is 18–21; be a little generous
function mockWindow(text: string): [number, number] | null {
  const m = text.match(/\b(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\b/) // wizard writes 24h "18:00-20:00"
  if (!m) return null
  return [+m[1] + +m[2] / 60, +m[3] + +m[4] / 60]
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// Mock-only sample dashboard data, derived from the fixtures with dates shifted.
// Never used when VITE_MOCK=false.
const DAY = 86400000
function shifted(base: Request, id: string, days: number, text: string, dur: number, max: number): Request {
  const r = fx<Request>(base)
  const sh = (iso: string) => new Date(+new Date(iso) - days * DAY).toISOString()
  r.id = id; r.raw_text = text
  r.timeline = r.timeline.map((e) => ({ ...e, t: sh(e.t) }))
  r.shortlist = r.shortlist.map((s) => ({ ...s, claims: s.claims.map((c) => ({ ...c, fetched_at: sh(c.fetched_at) })) }))
  if (r.constraints) Object.assign(r.constraints, { duration_min: dur, max_inr: max, window_start: sh(r.constraints.window_start), window_end: sh(r.constraints.window_end) })
  if (r.booking) {
    const start = sh(r.booking.start)
    Object.assign(r.booking, { start, end: new Date(+new Date(start) + dur * 60000).toISOString() })
  }
  return r
}
const SAMPLES = new Map<string, Request>()
const SAMPLE_SAVED: Saved[] = []
function addSample(r: Request, createdDaysAgo: number) {
  SAMPLES.set(r.id, r)
  SAMPLE_SAVED.push({ id: r.id, text: r.raw_text, created_at: new Date(Date.now() - createdDaysAgo * DAY).toISOString() })
}
if (MOCK) {
  const b = booked as unknown as Request
  addSample(fx<Request>({ ...b, id: 'r_sample_tonight' }), 0.1)
  addSample(shifted(b, 'r_sample_qc', 1, 'Need a 30 min call yesterday evening with a quick commerce dark-store ops lead, budget 2500', 30, 2500), 1.2)
  addSample(shifted(b, 'r_sample_lm', 2, 'Need a 15 min call with someone who has run last-mile delivery in Tier-2 cities, budget 1500', 15, 1500), 2.3)
  const failed = shifted(escalated as unknown as Request, 'r_sample_fail', 4, 'Need a 20 min call today 9-10 PM with a cold chain expert, budget 800', 20, 800)
  failed.status = 'FAILED'; failed.escalation = null
  failed.timeline.push({ t: failed.timeline[failed.timeline.length - 1].t, step: 'FAILED', msg: 'No verified expert available under ₹800 in the window', source: 'code' })
  addSample(failed, 4.1)
  addSample(shifted(b, 'r_sample_d2c', 6, 'Need a 45 min working session on D2C fulfilment setup, budget 3000', 45, 3000), 6.2)
  mockState.set('r_sample_live', { flow: 'demo', since: Date.now() + 60 * 60000, resolved: false }) // stays NEGOTIATING
  SAMPLE_SAVED.push({ id: 'r_sample_live', text: (negotiating as unknown as Request).raw_text, created_at: new Date(Date.now() - 4 * 60000).toISOString() })
  mockState.set('r_sample_esc', { flow: 'escalated', since: Date.now(), resolved: false })
  SAMPLE_SAVED.push({ id: 'r_sample_esc', text: 'Need a 20 min call tonight 7-8 with a warehouse automation expert, budget 2000', created_at: new Date(Date.now() - 25 * 60000).toISOString() })
  mockState.set('r_sample_clar', { flow: 'clarify', since: Date.now(), resolved: false })
  SAMPLE_SAVED.push({ id: 'r_sample_clar', text: 'Need to talk to a warehouse expert', created_at: new Date(Date.now() - 9 * 60000).toISOString() })
}
const hiddenSamples = new Set<string>()

function mockGet(id: string): Request {
  const sample = SAMPLES.get(id)
  if (sample) return fx<Request>(sample)
  const s = mockState.get(id) ?? { flow: 'demo' as const, since: Date.now(), resolved: false }
  mockState.set(id, s)
  const elapsed = Date.now() - s.since
  let r: Request
  if (s.flow === 'unavailable') {
    r = fx<Request>(escalated)
    r.escalation = { reason: 'No verified expert is free in the time window you picked.', options: [] }
    r.shortlist = r.shortlist.map((x) => ({ ...x, outreach_state: 'skipped' as const }))
    r.timeline = [...r.timeline.slice(0, 4), { t: r.timeline[3].t, step: 'ESCALATED', msg: 'No expert in the pool is available in that window', source: 'code' }]
  } else if (s.flow === 'clarify' && !s.resolved) r = fx<Request>(clarify)
  else if (s.flow === 'escalated' && !s.resolved) r = fx<Request>(escalated)
  else if (s.flow === 'escalated') r = fx<Request>(booked)
  else r = fx<Request>(elapsed < 5000 ? negotiating : booked)
  r.id = id
  const saved = SAMPLE_SAVED.find((x) => x.id === id)
  if (saved && r.status !== 'NEEDS_CLARIFICATION') r.raw_text = saved.text
  return r
}

// ---------------- public API ----------------
export async function createRequest(text: string): Promise<{ request_id: string; status: Status }> {
  let res: { request_id: string; status: Status }
  if (MOCK) {
    await sleep(300)
    const w = mockWindow(text)
    const flow: Flow = /escalat/i.test(text) ? 'escalated'
      : w && (w[1] <= MOCK_FREE[0] || w[0] >= MOCK_FREE[1]) ? 'unavailable'
      : /\d/.test(text) ? 'demo' : 'clarify'
    const id = `r_mock_${Date.now().toString(36)}`
    mockState.set(id, { flow, since: Date.now(), resolved: false })
    res = { request_id: id, status: 'INTAKE' }
  } else {
    res = await http('/requests', { method: 'POST', body: JSON.stringify({ text }) })
  }
  saveRequest({ id: res.request_id, text, created_at: new Date().toISOString() })
  return res
}

// "My requests" dashboard. No list endpoint in the contract yet, so we keep the IDs this
// browser created and fetch each with GET /requests/{id}. (Backend ask: GET /requests.)
export interface MyRequest { saved: Saved; req: Request | null; error?: string }
export async function listMyRequests(): Promise<MyRequest[]> {
  const mine = listSaved()
  const all = MOCK ? [...mine, ...SAMPLE_SAVED.filter((s) => !hiddenSamples.has(s.id))] : mine
  return Promise.all(all.map(async (saved) => {
    try { return { saved, req: await getRequest(saved.id) } }
    catch (e) { return { saved, req: null, error: (e as Error).message } }
  }))
}
export function removeMyRequest(id: string) {
  removeSaved(id)
  hiddenSamples.add(id)
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

// ---------------- auth (contract: "Auth: Sign in with Google") ----------------
export const REAL_GOOGLE = !MOCK
export function googleLoginUrl(redirect: string) {
  return `${BASE}/auth/google/login?redirect=${encodeURIComponent(redirect)}`
}
export async function getMe(token: string): Promise<AuthUser> {
  return http('/auth/me', { headers: { Authorization: `Bearer ${token}` } })
}
export async function logout(token: string) {
  if (MOCK) return
  await http('/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
}

// ---------------- chat with the booked expert (contract: "Chat" section) ----------------
// POST /requests/{id}/messages {expert_id, text}. Only when BOOKED and only with the booked expert.
// Real mode: replies arrive in the timeline (polling). Mock mode: replies are simulated locally.
export const CHAT_ENABLED = true
export const canChat = (r: Request, expertId?: string) => r.status === 'BOOKED' && !!r.booking && r.booking.expert_id === expertId
const MOCK_REPLIES = [
  'Hi! Yes, I can do that. Does 7:15 PM work for you?',
  'Sure. My usual rate is ₹1,800 for 20 minutes.',
  'Happy to help. Could you share 2–3 questions beforehand?',
  'Works for me. I will join from Google Meet.',
]
export async function sendChat(rid: string, expertId: string, text: string): Promise<ChatMsg> {
  if (!MOCK) {
    // The backend logs it to the timeline ("Client message relayed…"), which the chat panel renders.
    return http(`/requests/${encodeURIComponent(rid)}/messages`, { method: 'POST', body: JSON.stringify({ expert_id: expertId, text }) })
  }
  const mine = addChat(rid, { expert_id: expertId, from: 'me', text })
  setTimeout(() => {
    addChat(rid, { expert_id: expertId, from: 'expert', text: MOCK_REPLIES[Math.floor(Math.random() * MOCK_REPLIES.length)] })
  }, 2500 + Math.random() * 1500)
  return mine
}
export { listChat }
export type { ChatMsg }
