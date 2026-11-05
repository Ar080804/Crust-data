import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { Request, Status, ShortlistItem, Claim } from '../../../contract/types.ts'
import { getRequest, sendClarification, approveOption, sendChat, listChat, CHAT_ENABLED } from '../api.ts'
import { inr, time, clock, day } from '../format.ts'
import { Avatar, Confetti, Icon, Segmented, STATUS_ICON, STATUS_LABEL, SOURCE_ICON } from '../ui.tsx'
import Ticket from '../Ticket.tsx'
import { DecryptedText } from '../effects.tsx'

const POLL_MS = 1000
const STOP_ON: Status[] = ['BOOKED', 'FAILED']
const STEPS: Status[] = ['INTAKE', 'FINDING', 'VERIFYING', 'OUTREACH', 'NEGOTIATING', 'BOOKING', 'BOOKED']
const STEP_SHORT: Record<string, string> = {
  INTAKE: 'Understand', FINDING: 'Find', VERIFYING: 'Verify', OUTREACH: 'Reach out',
  NEGOTIATING: 'Negotiate', BOOKING: 'Book', BOOKED: 'Confirmed',
}

export default function RequestDetail() {
  const { id = '' } = useParams()
  const [req, setReq] = useState<Request | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [tick, setTick] = useState(0) // bump to restart polling after clarify/approve

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout>
    const loop = async () => {
      try {
        const r = await getRequest(id)
        if (!alive) return
        setReq(r); setErr(null)
        if (STOP_ON.includes(r.status)) return
      } catch (e) {
        if (alive) setErr((e as Error).message)
      }
      if (alive) timer = setTimeout(loop, POLL_MS)
    }
    loop()
    return () => { alive = false; clearTimeout(timer) }
  }, [id, tick])

  if (!req) {
    return <div className="loading">{err ? <><Icon name="alert" /> {err}</> : <><span className="spinner" /> Loading request…</>}</div>
  }

  const restart = () => setTick((t) => t + 1)

  return (
    <div className="detail">
      <div className="detail-top">
        <Link to="/new" className="back"><Icon name="back" size={14} /> New request</Link>
        <span className="mono muted small">{req.id}</span>
      </div>
      {err && <div className="banner warn"><Icon name="alert" /> Connection issue: {err}. Retrying…</div>}

      <section className="brief">
        <div className="brief-ask">
          <p className="kicker">The ask</p>
          <blockquote className="ask">{req.raw_text}</blockquote>
          {req.constraints ? <Constraints c={req.constraints} /> : <p className="muted small">Constraints not parsed yet.</p>}
        </div>
        <div className="brief-now">
          {req.booking ? <Booked req={req} /> : <NowPanel req={req} />}
        </div>
      </section>

      {req.status === 'NEEDS_CLARIFICATION' && <ClarifyBox req={req} onDone={restart} />}
      {req.status === 'ESCALATED' && req.escalation && <EscalationBox req={req} onDone={restart} />}
      {req.status === 'FAILED' && <NoProvider req={req} />}

      <Thread req={req} />

      <ChatPanel req={req} />

      <div className="cols">
        <Verification items={req.shortlist} req={req} />
        <AgentLog req={req} />
      </div>
    </div>
  )
}

/* ---------- brief ---------- */
function Constraints({ c }: { c: NonNullable<Request['constraints']> }) {
  return (
    <div className="facts">
      <div className="fact"><Icon name="users" size={14} /><span>{c.topic}</span></div>
      <div className="fact"><Icon name="clock" size={14} /><span>{c.duration_min} min</span></div>
      <div className="fact"><Icon name="calendar" size={14} /><span>{day(c.window_start)}, {time(c.window_start)} – {time(c.window_end)}</span></div>
      <div className="fact"><Icon name="chart" size={14} /><span>up to {inr(c.max_inr)}</span></div>
    </div>
  )
}

function agentSeconds(req: Request) {
  const t = req.timeline
  if (t.length < 2) return 0
  return Math.max(0, Math.round((+new Date(t[t.length - 1].t) - +new Date(t[0].t)) / 1000))
}
const fmtSecs = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`)

function NowPanel({ req }: { req: Request }) {
  const last = req.timeline[req.timeline.length - 1]
  const tone = req.status === 'FAILED' ? 'bad' : req.status === 'ESCALATED' || req.status === 'NEEDS_CLARIFICATION' ? 'warn' : 'live'
  return (
    <div className={`now spot now-${tone} ${tone === 'live' ? 'star-border' : ''}`}>
      <div className="now-head">
        <span className="now-dot" />
        <span className="kicker">{tone === 'live' ? 'Agent is working' : 'Paused'}</span>
        <span className="mono muted small push">{fmtSecs(agentSeconds(req))}</span>
      </div>
      <div className="now-status">
        <Icon name={STATUS_ICON[req.status] ?? 'sparkle'} size={22} />
        {STATUS_LABEL[req.status] ?? req.status}
      </div>
      {last && <p className="now-msg">{last.msg}</p>}
      {last && <p className="mono muted small">{clock(last.t)} · {last.source}</p>}
    </div>
  )
}

function Booked({ req }: { req: Request }) {
  const b = req.booking!
  const who = req.shortlist.find((s) => s.expert_id === b.expert_id)
  const [hm, ...rest] = b.confirmation.split(',')
  return (
    <div className="booked-wrap glow-ok">
      <Confetti />
      <Ticket time={hm || time(b.start)} date={day(b.start)}
        range={`${time(b.start)} – ${time(b.end)}${req.constraints ? ` · ${req.constraints.duration_min} min` : ''}`}
        price={rest.join(',').trim() || inr(b.price_inr)} name={who?.name ?? b.expert_id} headline={who?.headline}
        eventId={b.calendar_event_id} confirmation={b.confirmation} />
      <p className="mono muted small center">Done in {fmtSecs(agentSeconds(req))} · {req.timeline.length} logged steps</p>
    </div>
  )
}

/* ---------- thread (stepper) ---------- */
function Thread({ req }: { req: Request }) {
  let idx = STEPS.indexOf(req.status)
  if (idx < 0) {
    const last = [...req.timeline].reverse().find((e) => STEPS.includes(e.step))
    idx = last ? STEPS.indexOf(last.step) : 0
  }
  const exception = !STEPS.includes(req.status)
  const done = req.status === 'BOOKED'
  const pct = done ? 100 : (idx / (STEPS.length - 1)) * 100
  return (
    <section className="thread" aria-label="Progress">
      <div className="thread-line"><span style={{ width: `${pct}%` }} /></div>
      <ol>
        {STEPS.map((s, i) => {
          const st = done || i < idx ? 'done' : i === idx ? (exception ? (req.status === 'FAILED' ? 'fail' : 'hold') : 'active') : 'todo'
          return (
            <li key={s} className={st}>
              <span className="bead">
                <Icon name={st === 'done' ? 'check' : st === 'fail' ? 'x' : st === 'hold' ? 'alert' : STATUS_ICON[s]} size={14} />
              </span>
              <span className="bead-lbl">{STEP_SHORT[s]}</span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

/* ---------- verification ---------- */
const VERDICT: Record<ShortlistItem['flag'], { t: string; cls: string; i: 'check' | 'help' | 'x' }> = {
  ok: { t: 'Verified', cls: 'ok', i: 'check' },
  unverifiable: { t: 'Unverifiable', cls: 'warn', i: 'help' },
  contradicted: { t: 'Contradicted', cls: 'bad', i: 'x' },
}
const CLAIM_V: Record<Claim['status'], { cls: string; i: 'check' | 'help' | 'x'; t: string }> = {
  verified: { cls: 'ok', i: 'check', t: 'Matches' },
  unverifiable: { cls: 'warn', i: 'help', t: 'No record' },
  contradicted: { cls: 'bad', i: 'x', t: 'Contradicts' },
}
const OUTREACH_TXT: Record<ShortlistItem['outreach_state'], string> = {
  pending: 'Not contacted', contacted: 'Messaged', replied: 'Replied', declined: 'Declined',
  timed_out: 'No reply', booked: 'Booked', released: 'Released', skipped: 'Skipped',
}
type ListFilter = 'all' | 'ok' | 'flagged'

function Verification({ items, req }: { items: ShortlistItem[]; req: Request }) {
  const [f, setF] = useState<ListFilter>('all')
  const okN = items.filter((x) => x.flag === 'ok').length
  const shown = items.filter((x) => f === 'all' || (f === 'ok' ? x.flag === 'ok' : x.flag !== 'ok'))
  const caught = items.filter((x) => x.flag === 'contradicted').length
  return (
    <section className="panel spot">
      <div className="panel-head">
        <div>
          <h2 className="h2">Shortlist &amp; verification</h2>
          <p className="muted small">
            {items.length} candidates · {okN} verified · {caught} fake {caught === 1 ? 'claim' : 'claims'} caught · source: Crustdata
          </p>
        </div>
        <Segmented value={f} onChange={setF} options={[
          { value: 'all', label: 'All', count: items.length },
          { value: 'ok', label: 'Verified', count: okN },
          { value: 'flagged', label: 'Flagged', count: items.length - okN },
        ]} />
      </div>
      {items.length === 0 && <p className="muted empty"><span className="spinner" /> Finding candidates…</p>}
      <div className="cands">
        {shown.map((x) => <Candidate key={x.expert_id} x={x} req={req} />)}
      </div>
    </section>
  )
}

function Candidate({ x, req }: { x: ShortlistItem; req: Request }) {
  const v = VERDICT[x.flag]
  const booked = req.booking?.expert_id === x.expert_id
  const over = req.constraints ? x.rate_inr > req.constraints.max_inr : false
  return (
    <article className={`cand spot cand-${v.cls} ${booked ? 'is-booked' : ''}`}>
      <div className="cand-head">
        <Avatar name={x.name} size={42} />
        <div className="cand-id">
          <div className="row wrap gap-s">
            <span className="strong">{x.name}</span>
            {booked && <span className="tag tag-ok"><Icon name="calendar" size={12} /> Booked</span>}
          </div>
          <div className="muted small">{x.headline}</div>
        </div>
        <div className="cand-right">
          <div className="rate">{inr(x.rate_inr)}{over && <span className="tag tag-warn">over budget</span>}</div>
          <div className="muted small">{OUTREACH_TXT[x.outreach_state]}</div>
        </div>
      </div>

      <div className="cand-meta">
        <span className={`stamp stamp-${v.cls}`}><Icon name={v.i} size={13} /> {v.t}</span>
        <div className="match" title="Match score">
          <span className="muted small">match</span>
          <span className="match-bar"><span style={{ width: `${Math.round(x.score * 100)}%` }} /></span>
          <span className="mono small">{Math.round(x.score * 100)}</span>
        </div>
      </div>

      <div className="claims">
        {x.claims.map((c, i) => {
          const cv = CLAIM_V[c.status]
          return (
            <div key={i} className={`claim claim-${cv.cls}`}>
              <div className="claim-col">
                <span className="claim-k">Claimed</span>
                <span className={c.status === 'contradicted' ? 'struck' : ''}>{c.text}</span>
              </div>
              <span className={`claim-v v-${cv.cls}`} title={c.status}><Icon name={cv.i} size={14} /><span>{cv.t}</span></span>
              <div className="claim-col">
                <span className="claim-k">Crustdata says</span>
                {(() => {
                  const ev = c.evidence ? c.evidence.replace(/^Crustdata( shows)?( only)?:\s*/i, '') : '—'
                  return c.status === 'contradicted' ? <DecryptedText text={ev} /> : <span>{ev}</span>
                })()}
              </div>
              <div className="claim-src mono">{c.source} · {clock(c.fetched_at)}</div>
            </div>
          )
        })}
      </div>
    </article>
  )
}

/* ---------- agent log ---------- */
function AgentLog({ req }: { req: Request }) {
  const box = useRef<HTMLOListElement>(null)
  const [src, setSrc] = useState('all')
  const sources = useMemo(() => Array.from(new Set(req.timeline.map((e) => e.source))), [req.timeline])
  const shown = req.timeline.filter((e) => src === 'all' || e.source === src)
  const live = !STOP_ON.includes(req.status)
  useEffect(() => { const el = box.current; if (el) el.scrollTop = el.scrollHeight }, [req.timeline.length])
  return (
    <section className="panel log spot">
      <div className="panel-head">
        <div>
          <h2 className="h2">Agent log</h2>
          <p className="muted small">Append-only audit trail · {req.timeline.length} events</p>
        </div>
        {live && <span className="tag tag-live"><span className="live-dot" /> Live</span>}
      </div>
      <div className="chips chips-sm">
        {['all', ...sources].map((s) => (
          <button type="button" key={s} className={`chip ${src === s ? 'on' : ''}`} onClick={() => setSrc(s)}>
            {s !== 'all' && <Icon name={SOURCE_ICON[s] ?? 'code'} size={12} />} {s}
          </button>
        ))}
      </div>
      <ol className="events" ref={box}>
        {shown.map((e, i) => (
          <li key={`${e.t}-${i}`} className={`ev src-${e.source}`}>
            <span className="ev-icon"><Icon name={SOURCE_ICON[e.source] ?? 'code'} size={13} /></span>
            <div className="ev-body">
              <div className="ev-meta">
                <span className="mono">{clock(e.t)}</span>
                <span className="ev-step">{e.step.replace('_', ' ')}</span>
                <span className="ev-src">{e.source}</span>
              </div>
              <div className="ev-msg">{e.msg}</div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

/* ---------- no provider available ---------- */
function NoProvider({ req }: { req: Request }) {
  const reason = req.escalation?.reason
    ?? [...req.timeline].reverse().find((e) => e.step === 'FAILED' || e.step === 'ESCALATED')?.msg
    ?? 'No verified expert could take this request.'
  return (
    <section className="noprov">
      <span className="noprov-icon"><Icon name="users" size={22} /></span>
      <div className="grow">
        <p className="kicker">No service provider available</p>
        <p className="action-q">{reason}</p>
        <p className="muted small">
          {req.constraints ? <>You asked for {day(req.constraints.window_start)}, {time(req.constraints.window_start)} – {time(req.constraints.window_end)}, up to {inr(req.constraints.max_inr)}. </> : null}
          Try a different time slot or a slightly higher budget.
        </p>
        <div className="row wrap action-row">
          <Link to="/new" className="btn btn-primary" data-cursor="Retry"><Icon name="calendar" /> Pick another slot</Link>
          <Link to="/experts" className="btn btn-ghost">Browse experts</Link>
        </div>
      </div>
    </section>
  )
}

/* ---------- chat with experts ---------- */
type Bubble = { key: string; from: 'agent' | 'expert' | 'me'; text: string; t: string; note?: string }

function ChatPanel({ req }: { req: Request }) {
  const people = req.shortlist.filter((x) => x.flag !== 'contradicted')
  const preferred = req.booking?.expert_id
    ?? people.find((x) => x.outreach_state === 'replied' || x.outreach_state === 'contacted')?.expert_id
    ?? people[0]?.expert_id
  const [sel, setSel] = useState<string | undefined>(preferred)
  const [, force] = useState(0)
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const f = (e: Event) => { if ((e as CustomEvent).detail === req.id) force((n) => n + 1) }
    window.addEventListener('sutradhar-chat', f)
    return () => window.removeEventListener('sutradhar-chat', f)
  }, [req.id])
  useEffect(() => { if (!sel && preferred) setSel(preferred) }, [sel, preferred])

  const expert = people.find((x) => x.expert_id === sel)
  const bubbles: Bubble[] = []
  if (expert) {
    const first = expert.name.split(' ')[0]
    req.timeline.forEach((e, i) => {
      if (e.source === 'telegram' && e.msg.includes(expert.name)) bubbles.push({ key: `t${i}`, from: 'agent', text: e.msg, t: e.t, note: 'Sent by agent via Telegram' })
      const q = e.msg.match(/^Reply "([^"]+)"/)
      if (q && (expert.outreach_state === 'replied' || expert.outreach_state === 'booked' || e.msg.includes(first))) {
        bubbles.push({ key: `r${i}`, from: 'expert', text: q[1], t: e.t, note: e.msg.replace(/^Reply "[^"]+"\s*/, '') })
      }
    })
    listChat(req.id).filter((m) => m.expert_id === expert.expert_id)
      .forEach((m) => bubbles.push({ key: m.id, from: m.from === 'me' ? 'me' : 'expert', text: m.text, t: m.t }))
    bubbles.sort((a, b) => +new Date(a.t) - +new Date(b.t))
  }
  const lastMine = [...bubbles].reverse().find((b) => b.from === 'me')
  const waiting = !!lastMine && !bubbles.some((b) => b.from === 'expert' && +new Date(b.t) > +new Date(lastMine.t))
  useEffect(() => { const el = box.current; if (el) el.scrollTop = el.scrollHeight }, [bubbles.length, waiting])

  if (people.length === 0) return null

  async function send(e: React.FormEvent) {
    e.preventDefault()
    if (!text.trim() || !expert) return
    setErr(null)
    try { await sendChat(req.id, expert.expert_id, text.trim()); setText('') }
    catch (ex) { setErr((ex as Error).message) }
  }

  return (
    <section className="panel chat spot">
      <div className="panel-head">
        <div>
          <h2 className="h2">Conversation</h2>
          <p className="muted small">Talk to experts directly. Messages are saved in your request history.</p>
        </div>
      </div>
      <div className="chat-grid">
        <div className="chat-people">
          {people.map((x) => (
            <button key={x.expert_id} type="button" className={`chat-person ${sel === x.expert_id ? 'on' : ''}`} onClick={() => setSel(x.expert_id)}>
              <Avatar name={x.name} size={34} />
              <span className="grow">
                <span className="strong block">{x.name}</span>
                <span className="muted small">{OUTREACH_TXT[x.outreach_state]}</span>
              </span>
              {listChat(req.id).some((m) => m.expert_id === x.expert_id) && <span className="dot-new" />}
            </button>
          ))}
        </div>
        <div className="chat-main">
          <div className="chat-msgs" ref={box}>
            {bubbles.length === 0 && <p className="muted small center chat-empty">No messages yet. Say hi to {expert?.name.split(' ')[0]}.</p>}
            {bubbles.map((b) => (
              <div key={b.key} className={`bubble b-${b.from}`}>
                <div>{b.text}</div>
                <div className="bubble-meta">{b.from === 'agent' ? 'Agent' : b.from === 'me' ? 'You' : expert?.name.split(' ')[0]} · {clock(b.t)}{b.note ? ` · ${b.note}` : ''}</div>
              </div>
            ))}
            {waiting && <div className="bubble b-expert typing"><span /><span /><span /></div>}
          </div>
          <form className="chat-compose" onSubmit={send}>
            <input value={text} onChange={(e) => setText(e.target.value)} disabled={!CHAT_ENABLED}
              placeholder={CHAT_ENABLED ? `Message ${expert?.name.split(' ')[0] ?? ''}…` : 'Direct chat will turn on when the backend supports it'} />
            <button className="btn btn-primary" disabled={!CHAT_ENABLED || !text.trim()} data-cursor="Send"><Icon name="send" size={15} /> Send</button>
          </form>
          {waiting && <p className="muted small chat-wait"><span className="spinner" /> Waiting for {expert?.name.split(' ')[0]} to reply…</p>}
          {!CHAT_ENABLED && <p className="muted small chat-wait">Read-only for now: shows the agent's Telegram messages and the expert's replies.</p>}
          {err && <p className="error"><Icon name="alert" /> {err}</p>}
        </div>
      </div>
    </section>
  )
}

/* ---------- actions ---------- */
function ClarifyBox({ req, onDone }: { req: Request; onDone: () => void }) {
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const QUICK = ['Tomorrow 6–8 PM, budget ₹2000', 'Today evening, budget ₹1500', 'Any time this week, budget ₹3000']
  async function submit(e?: React.FormEvent) {
    e?.preventDefault()
    if (!answer.trim()) return
    setBusy(true); setErr(null)
    try { await sendClarification(req.id, answer.trim()); setAnswer(''); onDone() }
    catch (ex) { setErr((ex as Error).message) }
    finally { setBusy(false) }
  }
  return (
    <form className="action-card warn" onSubmit={submit}>
      <Icon name="help" size={20} />
      <div className="grow">
        <p className="kicker">The agent needs one detail</p>
        <p className="action-q">{req.clarification_question}</p>
        <div className="chips">
          {QUICK.map((q) => <button type="button" key={q} className="chip" onClick={() => setAnswer(q)}>{q}</button>)}
        </div>
        <div className="row action-row">
          <input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Type your answer" autoFocus />
          <button className="btn btn-primary" disabled={busy || !answer.trim()}>{busy ? 'Sending…' : <>Answer <Icon name="arrow" /></>}</button>
        </div>
        {err && <p className="error"><Icon name="alert" /> {err}</p>}
      </div>
    </form>
  )
}

function EscalationBox({ req, onDone }: { req: Request; onDone: () => void }) {
  const esc = req.escalation!
  const options = esc.options ?? []
  const [pick, setPick] = useState(options[0]?.option_id ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const nameOf = (eid: string) => req.shortlist.find((s) => s.expert_id === eid)?.name ?? eid
  if (options.length === 0) return <NoProvider req={req} />
  async function approve() {
    setBusy(true); setErr(null)
    try { await approveOption(req.id, pick); onDone() }
    catch (ex) { setErr((ex as Error).message) }
    finally { setBusy(false) }
  }
  return (
    <section className="action-card warn">
      <Icon name="hand" size={20} />
      <div className="grow">
        <p className="kicker">{options.length ? 'Your approval needed' : 'Escalated to a human'}</p>
        <p className="action-q">{esc.reason}</p>
        {options.length === 0 ? (
          <p className="muted small">No bookable option right now. The team will follow up.</p>
        ) : (
          <>
            <div className="options">
              {options.map((o) => {
                const over = req.constraints ? o.price_inr - req.constraints.max_inr : 0
                return (
                  <label key={o.option_id} className={`option ${pick === o.option_id ? 'sel' : ''}`}>
                    <input type="radio" name="opt" checked={pick === o.option_id} onChange={() => setPick(o.option_id)} />
                    <Avatar name={nameOf(o.expert_id)} size={34} />
                    <div className="grow">
                      <div className="strong">{o.summary}</div>
                      <div className="muted small">{day(o.slot)}, {time(o.slot)} · {inr(o.price_inr)}</div>
                    </div>
                    {over > 0 && <span className="tag tag-warn">+{inr(over)} over budget</span>}
                  </label>
                )
              })}
            </div>
            <button className="btn btn-primary" onClick={approve} disabled={busy || !pick}>
              {busy ? 'Approving…' : <><Icon name="check" /> Approve &amp; book</>}
            </button>
          </>
        )}
        {err && <p className="error"><Icon name="alert" /> {err}</p>}
      </div>
    </section>
  )
}
