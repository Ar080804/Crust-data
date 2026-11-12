import type { Expert, Request, ShortlistItem, TimelineEvent } from '../../contract/types.ts'

// This scenario is authored specifically for the public demo. It has no contact details.
const simulatedDay = new Date(Date.now() + 86_400_000 + 19_800_000).toISOString().slice(0, 10)
const at = (time: string) => `${simulatedDay}T${time}+05:30`

const items: ShortlistItem[] = [
  {
    expert_id: 'sample-a', name: 'Demo Expert A', headline: 'Sample warehouse operations profile',
    rate_inr: 1400, score: 0.9, flag: 'ok', outreach_state: 'pending',
    claims: [{ text: 'Warehouse operations', status: 'verified', evidence: 'Matches the synthetic skill record.', source: 'demo', fetched_at: at('10:00:00') }],
  },
  {
    expert_id: 'sample-b', name: 'Demo Expert B', headline: 'Sample inventory profile',
    rate_inr: 1150, score: 0.6, flag: 'unverifiable', outreach_state: 'pending',
    claims: [{ text: 'Inventory planning', status: 'unverifiable', evidence: 'The synthetic record has no matching skill.', source: 'demo', fetched_at: at('10:00:00') }],
  },
  {
    expert_id: 'sample-c', name: 'Demo Expert C', headline: 'Sample fulfilment profile',
    rate_inr: 1250, score: 0, flag: 'contradicted', outreach_state: 'skipped',
    claims: [{ text: 'Fulfilment supervision', status: 'contradicted', evidence: 'The synthetic record contains a different skill.', source: 'demo', fetched_at: at('10:00:00') }],
  },
]

export const expertsFx: { experts: Expert[] } = {
  experts: items.map(({ expert_id, name, headline, rate_inr }) => ({
    expert_id, name, headline, rate_inr, simulated: true, linkedin_url: '',
  })),
}
const events: TimelineEvent[] = [
  { t: at('10:00:00'), step: 'INTAKE', source: 'simulator', msg: 'Parsed the sample request.' },
  { t: at('10:00:01'), step: 'FINDING', source: 'simulator', msg: 'Shortlisted three fictional profiles.' },
  { t: at('10:00:02'), step: 'VERIFYING', source: 'simulator', msg: 'Checked the synthetic skill records.' },
  { t: at('10:00:03'), step: 'OUTREACH', source: 'simulator', msg: 'Message to Demo Expert A via Telegram: "Would 6:30 pm work for the sample call?"' },
]
const sample: Request = {
  id: 'sample-request', status: 'NEGOTIATING', raw_text: 'Example request for a 20-minute warehouse call, 6–8 pm IST, budget ₹2,100.',
  clarification_question: null,
  constraints: { topic: 'warehouse operations', duration_min: 20, window_start: at('18:00:00'), window_end: at('20:00:00'), max_inr: 2100 },
  shortlist: items, timeline: events, booking: null, escalation: null,
}

function markFirst(state: ShortlistItem['outreach_state']): ShortlistItem[] {
  return items.map((item, i) => i === 0 ? { ...item, outreach_state: state } : item)
}

export const negotiating: Request = { ...sample, shortlist: markFirst('contacted') }
export const clarify: Request = {
  ...sample, status: 'NEEDS_CLARIFICATION', constraints: null, shortlist: [], timeline: events.slice(0, 1),
  clarification_question: 'What is your time window and budget?',
}
export const escalated: Request = {
  ...sample, status: 'ESCALATED', shortlist: markFirst('declined'),
  escalation: { reason: 'The requested sample slot is full.', options: [{
    option_id: 'sample-later', expert_id: 'sample-a', slot: at('18:30:00'), price_inr: 1400, summary: 'Demo Expert A at 6:30 pm for ₹1,400',
  }] },
}
export const booked: Request = {
  ...sample, status: 'BOOKED', shortlist: markFirst('booked'),
  booking: { expert_id: 'sample-a', start: at('18:30:00'), end: at('18:50:00'), price_inr: 1400,
    calendar_event_id: 'sample-calendar-event', confirmation: '6:30 PM, ₹1,400' },
  timeline: [...events,
    { t: at('10:00:06'), step: 'NEGOTIATING', source: 'simulator', msg: 'Reply "6:30 works for ₹1,400" from Demo Expert A' },
    { t: at('10:00:07'), step: 'BOOKING', source: 'simulator', msg: 'Created a sample calendar record.' },
    { t: at('10:00:08'), step: 'BOOKED', source: 'simulator', msg: 'Sample receipt is ready.' },
  ],
}
