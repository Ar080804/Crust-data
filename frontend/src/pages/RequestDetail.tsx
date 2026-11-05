import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import type { Request, Status, ShortlistItem, Claim } from '../../../contract/types.ts'
import { getRequest, sendClarification, approveOption } from '../api.ts'
import { inr, time, clock, day } from '../format.ts'

const POLL_MS = 1000
const STOP_ON: Status[] = ['BOOKED', 'FAILED']
const STEPS: Status[] = ['INTAKE', 'FINDING', 'VERIFYING', 'OUTREACH', 'NEGOTIATING', 'BOOKING', 'BOOKED']

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

  if (!req) return <p className="muted">{err ? `⚠ ${err}` : 'Loading request…'}</p>

  const restart = () => setTick((t) => t + 1)

  return (
    <div className="detail">
      <div className="row between wrap">
        <div>
          <p className="eyebrow">Request {req.id}</p>
          <h2 className="quote">“{req.raw_text}”</h2>
        </div>
        <StatusPill status={req.status} />
      </div>
      {err && <p className="error">⚠ Connection issue: {err} (retrying…)</p>}

      <Stepper req={req} />

      {req.status === 'NEEDS_CLARIFICATION' && <ClarifyBox req={req} onDone={restart} />}
      {req.status === 'ESCALATED' && req.escalation && <EscalationBox req={req} onDone={restart} />}
      {req.status === 'FAILED' && <div className="card danger">The agent could not complete this request. See the timeline.</div>}
      {req.booking && <BookingCard req={req} />}

      <div className="grid2">
        <div className="col">
          {req.constraints && <ConstraintsCard c={req.constraints} />}
          <Shortlist items={req.shortlist} bookedId={req.booking?.expert_id} />
        </div>
        <Timeline req={req} />
      </div>
    </div>
  )
}

function StatusPill({ status }: { status: Status }) {
  const cls = status === 'BOOKED' ? 'ok' : status === 'FAILED' ? 'bad' : status === 'ESCALATED' || status === 'NEEDS_CLARIFICATION' ? 'warn' : 'info'
  return <span className={`pill big ${cls}`}>{status === 'BOOKED' ? '✓ ' : ''}{status.replace('_', ' ')}</span>
}

function Stepper({ req }: { req: Request }) {
  // For exception states, show where we were using the last main-path step in the timeline.
  let idx = STEPS.indexOf(req.status)
  if (idx < 0) {
    const last = [...req.timeline].reverse().find((e) => STEPS.includes(e.step))
    idx = last ? STEPS.indexOf(last.step) : 0
  }
  const exception = idx >= 0 && !STEPS.includes(req.status)
  const done = req.status === 'BOOKED'
  return (
    <ol className="stepper">
      {STEPS.map((s, i) => {
        const state = done || i < idx ? 'done' : i === idx ? (exception ? (req.status === 'FAILED' ? 'fail' : 'hold') : 'active') : ''
        return (
          <li key={s} className={state}>
            <span className="dot">{state === 'done' ? '✓' : state === 'fail' ? '✕' : state === 'hold' ? '!' : i + 1}</span>
            <span className="lbl">{s}</span>
          </li>
        )
      })}
    </ol>
  )
}

function ConstraintsCard({ c }: { c: NonNullable<Request['constraints']> }) {
  return (
    <section className="card">
      <h3>Constraints</h3>
      <dl className="kv">
        <div><dt>Topic</dt><dd>{c.topic}</dd></div>
        <div><dt>Duration</dt><dd>{c.duration_min} min</dd></div>
        <div><dt>Window</dt><dd>{day(c.window_start)}, {time(c.window_start)} – {time(c.window_end)}</dd></div>
        <div><dt>Budget</dt><dd>≤ {inr(c.max_inr)}</dd></div>
      </dl>
    </section>
  )
}

const CLAIM_ICON: Record<Claim['status'], string> = { verified: '🟢', unverifiable: '🟡', contradicted: '🔴' }
const FLAG_CLS: Record<ShortlistItem['flag'], string> = { ok: 'ok', unverifiable: 'warn', contradicted: 'bad' }

function Shortlist({ items, bookedId }: { items: ShortlistItem[]; bookedId?: string }) {
  return (
    <section className="card">
      <h3>Shortlist <span className="muted small">· claims checked against Crustdata</span></h3>
      {items.length === 0 && <p className="muted">No candidates yet…</p>}
      <ul className="experts">
        {items.map((x) => (
          <li key={x.expert_id} className={`expert ${x.flag} ${x.expert_id === bookedId ? 'booked' : ''}`}>
            <div className="row between wrap">
              <div>
                <strong>{x.name}</strong> {x.expert_id === bookedId && <span className="pill ok">BOOKED</span>}
                <div className="muted small">{x.headline}</div>
              </div>
              <div className="right">
                <div className="mono">{inr(x.rate_inr)}</div>
                <span className={`pill ${FLAG_CLS[x.flag]}`}>{x.flag}</span>{' '}
                <span className="pill">{x.outreach_state.replace('_', ' ')}</span>
              </div>
            </div>
            <div className="score" title={`score ${x.score.toFixed(2)}`}><span style={{ width: `${Math.round(x.score * 100)}%` }} /></div>
            <ul className="claims">
              {x.claims.map((c, i) => (
                <li key={i} className={`claim ${c.status}`}>
                  <div><span aria-hidden>{CLAIM_ICON[c.status]}</span> <b>{c.status}</b>: {c.text}</div>
                  {c.evidence && <div className="evidence">↳ {c.evidence}</div>}
                  <div className="muted small mono">source: {c.source} · {clock(c.fetched_at)}</div>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Timeline({ req }: { req: Request }) {
  const end = useRef<HTMLLIElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [req.timeline.length])
  return (
    <section className="card timeline">
      <h3>Live audit log <span className="live">● live</span></h3>
      <ol>
        {req.timeline.map((e, i) => (
          <li key={i} ref={i === req.timeline.length - 1 ? end : undefined}>
            <span className="mono muted small">{clock(e.t)}</span>
            <span className="step">{e.step}</span>
            <span className={`src src-${e.source}`}>{e.source}</span>
            <div className="msg">{e.msg}</div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function BookingCard({ req }: { req: Request }) {
  const b = req.booking!
  const who = req.shortlist.find((s) => s.expert_id === b.expert_id)
  return (
    <section className="card booking">
      <p className="eyebrow">Booked ✓</p>
      <div className="confirm">{b.confirmation}</div>
      <p>
        {who ? <strong>{who.name}</strong> : b.expert_id} · {day(b.start)}, {time(b.start)} – {time(b.end)} · {inr(b.price_inr)}
      </p>
      <p className="muted small mono">calendar event: {b.calendar_event_id}</p>
    </section>
  )
}

function ClarifyBox({ req, onDone }: { req: Request; onDone: () => void }) {
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try { await sendClarification(req.id, answer.trim()); setAnswer(''); onDone() }
    catch (ex) { setErr((ex as Error).message) }
    finally { setBusy(false) }
  }
  return (
    <form className="card attention" onSubmit={submit}>
      <h3>The agent needs one more detail</h3>
      <p className="question">{req.clarification_question}</p>
      <div className="row">
        <input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="e.g. tomorrow 6–8 PM, budget ₹2000" autoFocus />
        <button disabled={busy || !answer.trim()}>{busy ? 'Sending…' : 'Answer'}</button>
      </div>
      {err && <p className="error">⚠ {err}</p>}
    </form>
  )
}

function EscalationBox({ req, onDone }: { req: Request; onDone: () => void }) {
  const esc = req.escalation!
  const [pick, setPick] = useState(esc.options[0]?.option_id ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function approve() {
    setBusy(true); setErr(null)
    try { await approveOption(req.id, pick); onDone() }
    catch (ex) { setErr((ex as Error).message) }
    finally { setBusy(false) }
  }
  return (
    <section className="card attention">
      <h3>Human approval needed</h3>
      <p>{esc.reason}</p>
      <div className="options">
        {esc.options.map((o) => (
          <label key={o.option_id} className={`option ${pick === o.option_id ? 'sel' : ''}`}>
            <input type="radio" name="opt" checked={pick === o.option_id} onChange={() => setPick(o.option_id)} />
            <div>
              <div>{o.summary}</div>
              <div className="muted small">{day(o.slot)}, {time(o.slot)} · {inr(o.price_inr)}</div>
            </div>
          </label>
        ))}
      </div>
      <button onClick={approve} disabled={busy || !pick}>{busy ? 'Approving…' : 'Approve'}</button>
      {err && <p className="error">⚠ {err}</p>}
    </section>
  )
}
