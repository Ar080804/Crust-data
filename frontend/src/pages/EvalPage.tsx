import { useEffect, useState } from 'react'
import type { Eval } from '../../../contract/types.ts'
import { getEval } from '../api.ts'
import { day, time } from '../format.ts'
import { Icon, useCountUp, type IconName } from '../ui.tsx'

export default function EvalPage() {
  const [ev, setEv] = useState<Eval | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { getEval().then(setEv).catch((e) => setErr(e.message)) }, [])

  if (err) return <div className="banner bad"><Icon name="alert" /> {err}</div>
  if (!ev) return <div className="loading"><span className="spinner" /> Loading eval…</div>
  const groups = Math.round(ev.total_runs / 3) || ev.consistent
  const allZero = ev.budget_violations + ev.double_bookings + ev.time_violations === 0
  const allCaught = ev.fakes_caught === ev.fakes_planted

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="kicker">Evaluation</p>
          <h1 className="display-sm">Report card</h1>
          <p className="muted">
            {ev.total_runs} runs: {groups} requests, each phrased 3 different ways. Last run {day(ev.run_at)}, {time(ev.run_at)}.
          </p>
        </div>
        <span className={`verdict ${allZero && allCaught ? 'ok' : 'bad'}`}>
          <Icon name={allZero && allCaught ? 'check' : 'alert'} size={16} /> {allZero && allCaught ? 'All checks passed' : 'Some checks failed'}
        </span>
      </header>

      <div className="hero-stats">
        <BigRatio value={ev.fakes_caught} total={ev.fakes_planted} label="planted fake claims caught"
          note="Profiles with made-up work history were slipped into the pool. Each one was flagged by the Crustdata check." />
        <BigRatio value={ev.consistent} total={groups} label="paraphrase groups gave the same result"
          note="Same request, three wordings. A consistent agent books the same outcome every time." />
      </div>

      <h2 className="h2 section-gap">Hard constraints: must be zero</h2>
      <div className="zeros">
        <Zero n={ev.budget_violations} label="Budget violations" hint="booked above the stated max" icon="chart" />
        <Zero n={ev.time_violations} label="Time-window violations" hint="booked outside the window" icon="clock" />
        <Zero n={ev.double_bookings} label="Double bookings" hint="same slot booked twice" icon="calendar" />
      </div>
    </div>
  )
}

function BigRatio({ value, total, label, note }: { value: number; total: number; label: string; note: string }) {
  const v = useCountUp(value)
  const pct = total > 0 ? Math.round((v / total) * 100) : 0
  const good = value === total
  return (
    <div className={`big spot ${good ? 'ok' : 'bad'}`}>
      <div className="big-num">{v}<span className="big-den">/{total}</span></div>
      <div className="big-lbl">{label}</div>
      <div className="big-bar"><span style={{ width: `${pct}%` }} /></div>
      <p className="muted small">{note}</p>
    </div>
  )
}

function Zero({ n, label, hint, icon }: { n: number; label: string; hint: string; icon: IconName }) {
  const v = useCountUp(n)
  const good = n === 0
  return (
    <div className={`zero spot ${good ? 'ok' : 'bad'}`}>
      <div className="zero-top">
        <span className="zero-icon"><Icon name={icon} size={16} /></span>
        <span className={`tag ${good ? 'tag-ok' : 'tag-bad'}`}><Icon name={good ? 'check' : 'x'} size={12} /> {good ? 'Pass' : 'Fail'}</span>
      </div>
      <div className="zero-num">{v}</div>
      <div className="strong">{label}</div>
      <div className="muted small">{hint}</div>
    </div>
  )
}
