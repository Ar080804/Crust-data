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
const DAYS = ['today', 'tomorrow', 'day after']
const WINDOWS: { v: string; label: string; icon: IconName }[] = [
  { v: '10-12 AM', label: 'Morning · 10–12', icon: 'sun' },
  { v: '2-4 PM', label: 'Afternoon · 2–4', icon: 'sun' },
  { v: '6-8 PM', label: 'Evening · 6–8', icon: 'moon' },
  { v: '8-10 PM', label: 'Late · 8–10', icon: 'moon' },
]
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
  const [day, setDay] = useState('tomorrow')
  const [win, setWin] = useState('6-8 PM')
  const [budget, setBudget] = useState(2000)
  const [notes, setNotes] = useState('')
  const [text, setText] = useState(prefill ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const composed = useMemo(() => {
    let s = `Need a ${duration} min call ${day} ${win} with someone experienced in ${topic.trim() || 'warehouse management'}, budget ${budget}`
    if (notes.trim()) s += `. ${notes.trim()}`
    return s
  }, [duration, day, win, topic, budget, notes])

  const canNext = step !== 0 || topic.trim().length > 1
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
              <p className="wiz-label">Day</p>
              <div className="tiles three">
                {DAYS.map((d) => (
                  <button type="button" key={d} className={`tile ${day === d ? 'on' : ''}`} onClick={() => setDay(d)}>
                    <Icon name="calendar" size={18} /><span className="tile-mid">{d[0].toUpperCase() + d.slice(1)}</span>
                  </button>
                ))}
              </div>
              <p className="wiz-label">Time window (IST)</p>
              <div className="tiles four">
                {WINDOWS.map((w) => (
                  <button type="button" key={w.v} className={`tile ${win === w.v ? 'on' : ''}`} onClick={() => setWin(w.v)}>
                    <Icon name={w.icon} size={18} /><span className="tile-mid">{w.label}</span>
                  </button>
                ))}
              </div>
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
                <span className="fact"><Icon name="calendar" size={14} />{day}, {win}</span>
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
