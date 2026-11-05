// Builds chat bubbles from the request timeline using the stable formats in
// contract/CONTRACT.md ("Timeline message formats the frontend relies on"), plus
// locally simulated messages in mock mode.
import type { Request, ShortlistItem } from '../../contract/types.ts'
import type { ChatMsg } from './history.ts'

export type Bubble = { key: string; from: 'agent' | 'expert' | 'me'; text: string; t: string; note?: string }

const RE_AGENT = /^Message to (.+?) via Telegram: "([\s\S]*)"$/
const RE_REPLY = /^Reply "([\s\S]*?)" from (.+?)(?: →| \(after booking\)|$)/
const RE_CLIENT = /^Client message relayed to the expert: "([\s\S]*)"$/
// older fixture formats (kept so mock data still renders)
const RE_OLD_SENT = /^Sent request to (.+?) via Telegram/
const RE_OLD_REPLY = /^Reply "([^"]+)" parsed/

export function chatBubbles(r: Request, expert: ShortlistItem, local: ChatMsg[]): Bubble[] {
  const out: Bubble[] = []
  const booked = r.booking?.expert_id === expert.expert_id
  r.timeline.forEach((e, i) => {
    let m: RegExpMatchArray | null
    if ((m = e.msg.match(RE_AGENT)) && m[1] === expert.name) {
      out.push({ key: `a${i}`, from: 'agent', text: m[2], t: e.t, note: 'sent by agent' })
    } else if ((m = e.msg.match(RE_REPLY)) && m[2].trim() === expert.name) {
      out.push({ key: `r${i}`, from: 'expert', text: m[1], t: e.t })
    } else if ((m = e.msg.match(RE_CLIENT)) && booked) {
      out.push({ key: `c${i}`, from: 'me', text: m[1], t: e.t })
    } else if ((m = e.msg.match(RE_OLD_SENT)) && m[1] === expert.name) {
      out.push({ key: `o${i}`, from: 'agent', text: e.msg, t: e.t, note: 'sent by agent' })
    } else if ((m = e.msg.match(RE_OLD_REPLY)) && (expert.outreach_state === 'replied' || booked)) {
      out.push({ key: `p${i}`, from: 'expert', text: m[1], t: e.t })
    }
  })
  local.filter((x) => x.expert_id === expert.expert_id)
    .forEach((x) => out.push({ key: x.id, from: x.from === 'me' ? 'me' : 'expert', text: x.text, t: x.t }))
  return out.sort((a, b) => +new Date(a.t) - +new Date(b.t))
}

/** Number of chat messages for a request (timeline + local), for the dashboard. */
export function chatCount(r: Request | null, local: ChatMsg[]): number {
  if (!r) return local.length
  const n = r.timeline.filter((e) => RE_AGENT.test(e.msg) || RE_REPLY.test(e.msg) || RE_CLIENT.test(e.msg)).length
  return n + local.length
}
