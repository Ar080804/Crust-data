import { useEffect, useState } from 'react'
import type { Eval } from '../../../contract/types.ts'
import { getEval } from '../api.ts'
import { day, time } from '../format.ts'

export default function EvalPage() {
  const [ev, setEv] = useState<Eval | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { getEval().then(setEv).catch((e) => setErr(e.message)) }, [])

  if (err) return <p className="error">⚠ {err}</p>
  if (!ev) return <p className="muted">Loading eval…</p>
  const groups = Math.round(ev.total_runs / 3) || ev.consistent
  const stats = [
    { n: ev.budget_violations, label: 'budget violations', good: ev.budget_violations === 0 },
    { n: ev.double_bookings, label: 'double bookings', good: ev.double_bookings === 0 },
    { n: ev.time_violations, label: 'time-window violations', good: ev.time_violations === 0 },
    { n: `${ev.fakes_caught}/${ev.fakes_planted}`, label: 'fake claims caught', good: ev.fakes_caught === ev.fakes_planted },
    { n: `${ev.consistent}/${groups}`, label: 'paraphrase groups consistent', good: ev.consistent === groups },
  ]
  return (
    <section>
      <h2>Evaluation</h2>
      <p className="muted">{ev.total_runs} runs · last run {day(ev.run_at)}, {time(ev.run_at)}</p>
      <div className="stats">
        {stats.map((s) => (
          <div key={s.label} className={`stat ${s.good ? 'good' : 'bad'}`}>
            <div className="num">{s.n}</div>
            <div className="lbl">{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  )
}
