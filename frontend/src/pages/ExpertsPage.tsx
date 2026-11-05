import { useEffect, useState } from 'react'
import type { Expert } from '../../../contract/types.ts'
import { getExperts, ONBOARDING_URL } from '../api.ts'
import { inr } from '../format.ts'
import { Avatar, Icon, LinkedInIcon, Segmented } from '../ui.tsx'

type Kind = 'all' | 'real' | 'sim'
type Sort = 'rate-asc' | 'rate-desc' | 'name'

export default function ExpertsPage() {
  const [list, setList] = useState<Expert[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<Kind>('all')
  const [sort, setSort] = useState<Sort>('rate-asc')
  useEffect(() => { getExperts().then((r) => setList(r.experts)).catch((e) => setErr(e.message)) }, [])

  if (err) return <div className="banner bad"><Icon name="alert" /> {err}</div>
  if (!list) return <div className="loading"><span className="spinner" /> Loading experts…</div>

  const needle = q.trim().toLowerCase()
  const shown = list
    .filter((x) => kind === 'all' || (kind === 'sim' ? x.simulated : !x.simulated))
    .filter((x) => !needle || `${x.name} ${x.headline}`.toLowerCase().includes(needle))
    .sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name) : sort === 'rate-asc' ? a.rate_inr - b.rate_inr : b.rate_inr - a.rate_inr)
  const real = list.filter((x) => !x.simulated).length
  const rates = list.map((x) => x.rate_inr)

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="kicker">Directory</p>
          <h1 className="display-sm">Expert pool</h1>
          <p className="muted">Everyone here opted in. Profiles marked <i>Simulated</i> are replayed by a labelled simulator, not real people.</p>
          <a className="expert-join inline" href={ONBOARDING_URL} target="_blank" rel="noreferrer" data-cursor="Join">
            <LinkedInIcon size={16} /> <b>Join as an expert →</b>
          </a>
        </div>
        <div className="kpis">
          <div className="kpi"><b>{list.length}</b><span>experts</span></div>
          <div className="kpi"><b>{real}</b><span>real people</span></div>
          {rates.length > 0 && <div className="kpi"><b>{inr(Math.min(...rates))}–{inr(Math.max(...rates)).replace('₹', '')}</b><span>rate per call</span></div>}
        </div>
      </header>

      <div className="toolbar">
        <label className="search">
          <Icon name="search" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or company" />
        </label>
        <Segmented value={kind} onChange={setKind} options={[
          { value: 'all', label: 'All', count: list.length },
          { value: 'real', label: 'Real', count: real },
          { value: 'sim', label: 'Simulated', count: list.length - real },
        ]} />
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
          <option value="rate-asc">Rate: low to high</option>
          <option value="rate-desc">Rate: high to low</option>
          <option value="name">Name: A to Z</option>
        </select>
      </div>

      {shown.length === 0 && <p className="muted empty">No experts match “{q}”.</p>}
      <div className="xgrid">
        {shown.map((x) => (
          <article key={x.expert_id} className={`xcard spot ${x.simulated ? 'is-sim' : ''}`}>
            <div className="xcard-top">
              <Avatar name={x.name} size={46} />
              {x.simulated ? <span className="tag tag-warn">Simulated</span> : <span className="tag tag-ok"><span className="dot-ok" /> Real</span>}
            </div>
            <div className="strong xname">{x.name}</div>
            <div className="muted small xhead">{x.headline}</div>
            <div className="xcard-foot">
              <div><span className="rate">{inr(x.rate_inr)}</span><span className="muted small"> / call</span></div>
              {x.linkedin_url?.trim() && (
                <a href={x.linkedin_url} target="_blank" rel="noreferrer" className="xlink">LinkedIn <Icon name="external" size={12} /></a>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
