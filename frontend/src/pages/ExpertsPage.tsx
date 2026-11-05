import { useEffect, useState } from 'react'
import type { Expert } from '../../../contract/types.ts'
import { getExperts } from '../api.ts'
import { inr } from '../format.ts'

export default function ExpertsPage() {
  const [list, setList] = useState<Expert[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { getExperts().then((r) => setList(r.experts)).catch((e) => setErr(e.message)) }, [])

  if (err) return <p className="error">⚠ {err}</p>
  if (!list) return <p className="muted">Loading experts…</p>
  return (
    <section>
      <h2>Expert pool</h2>
      <p className="muted">"Simulated" experts are replayed by a labelled simulator, not real people.</p>
      <div className="cards">
        {list.map((x) => (
          <article key={x.expert_id} className="card">
            <div className="row between">
              <strong>{x.name}</strong>
              {x.simulated ? <span className="pill warn">Simulated</span> : <span className="pill ok">Real</span>}
            </div>
            <p className="muted small">{x.headline}</p>
            <div className="row between">
              <span className="mono">{inr(x.rate_inr)}</span>
              {x.linkedin_url?.trim() && (
                <a href={x.linkedin_url} target="_blank" rel="noreferrer">LinkedIn ↗</a>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
