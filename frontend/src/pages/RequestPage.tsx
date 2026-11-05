// Step-by-step request builder. At the end it composes ONE sentence and sends it as
// POST /requests {"text"}: exactly the contract, no new fields.
import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { createRequest } from '../api.ts'
import { useUser } from '../auth.ts'
import { Icon, type IconName } from '../ui.tsx'
import { inr } from '../format.ts'

const TOPICS = ['warehouse management', 'quick commerce ops', 'last-mile delivery', 'supply chain planning', 'cold chain logistics', 'D2C fulfilment']
const DURATIONS = [{ v: 15, d: 'Quick sanity check' }, { v: 20, d: 'Focused Q&A' }, { v: 30, d: 'Deeper dive' }, { v: 45, d: 'Working session' }]
// Custom date + time slot. Times are minutes from midnight, IST.
const PRESETS: { from: number; to: number; label: string; icon: IconName }[] = [
  { from: 600, to: 720, label: 'Morning · 10–12', icon: 'sun' },
  { from: 840, to: 960, label: 'Afternoon · 2–4', icon: 'sun' },
  { from: 1080, to: 1200, label: 'Evening · 6–8', icon: 'moon' },
  { from: 1200, to: 1320, label: 'Late · 8–10', icon: 'moon' },
]
const TIMES = Array.from({ length: 33 }, (_, i) => 420 + i * 30) // 7:00 AM … 11:00 PM
const fmtTime = (m: number) => {
  const h = Math.floor(m / 60), mm = m % 60
  return `${((h + 11) % 12) + 1}:${String(mm).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}
const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const addDays = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return isoDay(d) }
const fmtDate = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' })
const BUDGETS = [1000, 1500, 2000, 3000]

const STEPS: { key: string; title: string; sub: string }[] = [
  { key: 'topic', title: 'Who do you want to talk to?', sub: 'Describe the expertise. Pick one or type your own.' },
  { key: 'duration', title: 'How long should the call be?', sub: 'Shorter calls are easier to book quickly.' },
  { key: 'when', title: 'When works for you?', sub: 'We only book inside this window.' },
  { key: 'budget', title: "What's your budget?", sub: 'Hard limit. The agent never books above it.' },
  { key: 'notes', title: 'Anything else we should know?', sub: 'Optional. Must-haves, companies, language…' },
  { key: 'review', title: 'Looks good?', sub: 'This is exactly what the agent will read. Edit if you like.' },
]

export default function RequestPage() {
  const nav = useNavigate()
  const user = useUser()
  // "Book again" from My requests jumps straight to the review step with the old sentence.
  const prefill = (useLocation().state as { prefill?: string } | null)?.prefill
  const [step, setStep] = useState(prefill ? STEPS.length - 1 : 0)
  const [dir, setDir] = useState<1 | -1>(1)
  const [topic, setTopic] = useState('')
  const [duration, setDuration] = useState(20)
  const [date, setDate] = useState(addDays(1))
  const [from, setFrom] = useState(1080)
  const [to, setTo] = useState(1200)
  const [budget, setBudget] = useState(2000)
  const [notes, setNotes] = useState('')
  const [text, setText] = useState(prefill ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const composed = useMemo(() => {
    let s = `Need a ${duration} min call on ${fmtDate(date)} between ${fmtTime(from)} and ${fmtTime(to)} IST with someone experienced in ${topic.trim() || 'warehouse management'}, budget ${budget}`
    if (notes.trim()) s += `. ${notes.trim()}`
    return s
  }, [duration, date, from, to, topic, budget, notes])

  // Slot validation: window must fit the call, and must not be in the past.
  const nowMin = new Date().getHours() * 60 + new Date().getMinutes()
  const slotErr = to - from < duration ? `Window is shorter than your ${duration} min call.`
    : date < addDays(0) ? 'That date is in the past.'
    : date === addDays(0) && from <= nowMin ? 'That time has already passed today.'
    : null
  const canNext = step === 0 ? topic.trim().length > 1 : STEPS[step].key === 'when' ? !slotErr : true
  const go = (n: number) => {
    const to = Math.max(0, Math.min(STEPS.length - 1, n))
    if (to === STEPS.length - 1) setText(composed) // build the sentence when arriving at review
    setDir(n > step ? 1 : -1); setErr(null); setStep(to)
  }

  async function submit() {
    if (!text.trim()) return
    setBusy(true); setErr(null)
    try {
      const { request_id } = await createRequest(text.trim())
      nav(`/requests/${request_id}`)
    } catch (e) { setErr((e as Error).message); setBusy(false) }
  }

  const s = STEPS[step]
  const last = step === STEPS.length - 1

  return (
    <div className="wizard">
      <div className="wiz-top">
        <span className="kicker">{user && user.provider !== 'guest' ? `New request · ${user.name.split(' ')[0]}` : 'New request'}</span>
        <span className="mono muted small">Step {step + 1} of {STEPS.length}</span>
      </div>
      <div className="wiz-progress">
        {STEPS.map((x, i) => (
          <button key={x.key} type="button" className={`wiz-seg ${i < step ? 'done' : i === step ? 'on' : ''}`}
            onClick={() => (i < step ? go(i) : undefined)} aria-label={x.title} />
        ))}
      </div>

      <form key={step} className={`wiz-card ${dir === 1 ? 'from-right' : 'from-left'}`}
        onSubmit={(e) => { e.preventDefault(); if (last) submit(); else if (canNext) go(step + 1) }}>
        <h1 className="wiz-title">{s.title}</h1>
        <p className="muted">{s.sub}</p>

        <div className="wiz-body">
          {s.key === 'topic' && (
            <>
              <input className="wiz-input" value={topic} onChange={(e) => setTopic(e.target.value)} autoFocus
                placeholder="e.g. someone who has managed a warehouse" />
              <div className="chips">
                {TOPICS.map((t) => <button type="button" key={t} className={`chip ${topic === t ? 'on' : ''}`} onClick={() => setTopic(t)}>{t}</button>)}
              </div>
            </>
          )}

          {s.key === 'duration' && (
            <div className="tiles four">
              {DURATIONS.map((d) => (
                <button type="button" key={d.v} className={`tile ${duration === d.v ? 'on' : ''}`} onClick={() => setDuration(d.v)}>
                  <span className="tile-big">{d.v}<small> min</small></span>
                  <span className="muted small">{d.d}</span>
                </button>
              ))}
            </div>
          )}

          {s.key === 'when' && (
            <>
              <p className="wiz-label">Date</p>
              <div className="date-row">
                {[0, 1, 2].map((n) => {
                  const d = addDays(n)
                  return (
                    <button type="button" key={n} className={`chip ${date === d ? 'on' : ''}`} onClick={() => setDate(d)}>
                      {n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : fmtDate(d).split(',')[0] + ', ' + fmtDate(d).split(' ')[1] + ' ' + fmtDate(d).split(' ')[2].slice(0, 3)}
                    </button>
                  )
                })}
                <label className="date-pick">
                  <Icon name="calendar" size={15} />
                  <input type="date" value={date} min={addDays(0)} max={addDays(30)} onChange={(e) => e.target.value && setDate(e.target.value)} />
                </label>
              </div>

              <p className="wiz-label">Time slot (IST)</p>
              <div className="tiles four">
                {PRESETS.map((p) => (
                  <button type="button" key={p.label} className={`tile ${from === p.from && to === p.to ? 'on' : ''}`} onClick={() => { setFrom(p.from); setTo(p.to) }}>
                    <Icon name={p.icon} size={18} /><span className="tile-mid">{p.label}</span>
                  </button>
                ))}
              </div>
              <div className="slot-custom">
                <span className="muted small">or custom:</span>
                <label className="slot-sel"><span>From</span>
                  <select value={from} onChange={(e) => { const v = +e.target.value; setFrom(v); if (to - v < duration) setTo(Math.min(1380, v + Math.max(60, duration))) }}>
                    {TIMES.slice(0, -1).map((m) => <option key={m} value={m}>{fmtTime(m)}</option>)}
                  </select>
                </label>
                <label className="slot-sel"><span>To</span>
                  <select value={to} onChange={(e) => setTo(+e.target.value)}>
                    {TIMES.filter((m) => m > from).map((m) => <option key={m} value={m}>{fmtTime(m)}</option>)}
                  </select>
                </label>
              </div>
              <div className={`slot-summary ${slotErr ? 'bad' : ''}`}>
                <Icon name={slotErr ? 'alert' : 'calendar'} size={15} />
                {slotErr ?? <span><b>{fmtDate(date)}</b>, {fmtTime(from)} – {fmtTime(to)} · we'll find a {duration} min slot inside this window</span>}
              </div>
              <p className="muted small">If no verified expert is free in this window, we'll tell you right away so you can pick another slot.</p>
            </>
          )}

          {s.key === 'budget' && (
            <div className="budget">
              <div className="budget-num">{inr(budget)}<span className="muted"> max per call</span></div>
              <input type="range" min={500} max={5000} step={100} value={budget} onChange={(e) => setBudget(+e.target.value)}
                style={{ ['--p' as string]: `${((budget - 500) / 4500) * 100}%` }} />
              <div className="range-scale mono small muted"><span>₹500</span><span>₹5,000</span></div>
              <div className="chips">
                {BUDGETS.map((b) => <button type="button" key={b} className={`chip ${budget === b ? 'on' : ''}`} onClick={() => setBudget(b)}>{inr(b)}</button>)}
              </div>
            </div>
          )}

          {s.key === 'notes' && (
            <textarea className="wiz-input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} autoFocus
              placeholder="e.g. Prefer someone from a quick-commerce startup. Hindi or English is fine." />
          )}

          {s.key === 'review' && (
            <>
              <div className="review-chips">
                <span className="fact"><Icon name="users" size={14} />{topic || 'warehouse management'}</span>
                <span className="fact"><Icon name="clock" size={14} />{duration} min</span>
                <span className="fact"><Icon name="calendar" size={14} />{fmtDate(date)}, {fmtTime(from)} – {fmtTime(to)}</span>
                <span className="fact"><Icon name="chart" size={14} />up to {inr(budget)}</span>
              </div>
              <textarea className="wiz-input review-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
            </>
          )}
        </div>

        {err && <p className="error"><Icon name="alert" /> {err}</p>}

        <div className="wiz-foot">
          {step > 0 ? <button type="button" className="btn btn-ghost" onClick={() => go(step - 1)}><Icon name="back" /> Back</button> : <span />}
          <div className="row">
            {s.key === 'notes' && <button type="button" className="btn btn-ghost" onClick={() => go(step + 1)}>Skip</button>}
            <button className="btn btn-primary btn-lg" disabled={!canNext || busy} data-cursor={last ? 'Book' : 'Next'}>
              {last ? (busy ? <><span className="spinner" /> Starting agent…</> : <>Find &amp; book expert <Icon name="arrow" /></>) : <>Continue <Icon name="arrow" /></>}
            </button>
          </div>
        </div>
        {!last && <p className="muted small center wiz-enter">Press <kbd>Enter</kbd> to continue</p>}
      </form>
    </div>
  )
}
