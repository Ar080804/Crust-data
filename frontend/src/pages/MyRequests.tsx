import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Request, Status } from '../../../contract/types.ts'
import { listMyRequests, removeMyRequest, listChat, MOCK, type MyRequest } from '../api.ts'
import { useUser } from '../auth.ts'
import { ago, day, inr, time, until } from '../format.ts'
import { Avatar, Icon, Segmented, STATUS_ICON, STATUS_LABEL } from '../ui.tsx'
import { Reveal } from '../cursor.tsx'

const STEPS: Status[] = ['INTAKE', 'FINDING', 'VERIFYING', 'OUTREACH', 'NEGOTIATING', 'BOOKING', 'BOOKED']
type Kind = 'action' | 'pending' | 'scheduled' | 'history'
type Tab = 'all' | Kind

function classify(m: MyRequest, now: number): Kind {
  const r = m.req
  if (!r) return 'history'
  if (r.status === 'NEEDS_CLARIFICATION' || r.status === 'ESCALATED') return 'action'
  if (r.status === 'FAILED') return 'history'
  if (r.status === 'BOOKED') return r.booking && +new Date(r.booking.end) > now ? 'scheduled' : 'history'
  return 'pending'
}

const gcalDate = (iso: string) => new Date(iso).toISOString().replace(/[-:]|\.\d{3}/g, '')
function gcalLink(r: Request, who: string) {
  const b = r.booking!
  const p = new URLSearchParams({
    action: 'TEMPLATE',
    text: `Expert call with ${who}`,
    dates: `${gcalDate(b.start)}/${gcalDate(b.end)}`,
    details: `Booked by Sutradhar.\nRequest: ${r.raw_text}\nPrice: ${inr(b.price_inr)}`,
  })
  return `https://calendar.google.com/calendar/render?${p}`
}

export default function MyRequests() {
  const user = useUser()
  const nav = useNavigate()
  const [items, setItems] = useState<MyRequest[] | null>(null)
  const [tab, setTab] = useState<Tab>('all')
  const [q, setQ] = useState('')
  const [now, setNow] = useState(Date.now())
  const [copied, setCopied] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    let t: ReturnType<typeof setTimeout>
    const load = async () => {
      const list = await listMyRequests()
      if (!alive) return
      setItems(list); setNow(Date.now())
      t = setTimeout(load, 5000)
    }
    load()
    return () => { alive = false; clearTimeout(t) }
  }, [])

  const groups = useMemo(() => {
    const g: Record<Kind, MyRequest[]> = { action: [], pending: [], scheduled: [], history: [] }
    const needle = q.trim().toLowerCase()
    for (const m of items ?? []) {
      if (needle && !`${m.saved.text} ${m.saved.id}`.toLowerCase().includes(needle)) continue
      g[classify(m, now)].push(m)
    }
    const created = (m: MyRequest) => +new Date(m.saved.created_at)
    g.action.sort((a, b) => created(b) - created(a))
    g.pending.sort((a, b) => created(b) - created(a))
    g.scheduled.sort((a, b) => +new Date(a.req!.booking!.start) - +new Date(b.req!.booking!.start))
    g.history = g.history.sort((a, b) => created(b) - created(a)).slice(0, 10)
    return g
  }, [items, q, now])

  if (!items) return <div className="loading"><span className="spinner" /> Loading your requests…</div>

  const remove = (id: string) => { removeMyRequest(id); setItems((xs) => xs?.filter((x) => x.saved.id !== id) ?? null) }
  const again = (text: string) => nav('/new', { state: { prefill: text } })
  const spent = [...groups.scheduled, ...groups.history].reduce((s, m) => s + (m.req?.status === 'BOOKED' ? m.req.booking?.price_inr ?? 0 : 0), 0)
  const next = groups.scheduled[0]?.req?.booking
  const show = (k: Kind) => tab === 'all' || tab === k
  const total = groups.action.length + groups.pending.length + groups.scheduled.length + groups.history.length

  return (
    <div className="page dash">
      <header className="page-head">
        <div>
          <p className="kicker">Dashboard</p>
          <h1 className="display-sm">{user && user.provider !== 'guest' ? `${user.name.split(' ')[0]}'s requests` : 'My requests'}</h1>
          <p className="muted">Everything you asked for: live, upcoming and done. Updates every few seconds.</p>
        </div>
        <Link to="/new" className="btn btn-primary" data-cursor="New"><Icon name="plus" /> New request</Link>
      </header>

      <div className="dash-stats">
        <Stat icon="alert" n={groups.action.length} label="need your action" tone={groups.action.length ? 'warn' : ''} />
        <Stat icon="message" n={groups.pending.length} label="in progress" tone="live" />
        <Stat icon="calendar" n={groups.scheduled.length} label={next ? `scheduled · next ${until(next.start, now)}` : 'scheduled'} />
        <Stat icon="check" n={groups.history.filter((m) => m.req?.status === 'BOOKED').length} label="completed" />
        <Stat icon="chart" n={inr(spent)} label="total booked" />
      </div>

      <div className="toolbar">
        <Segmented value={tab} onChange={setTab} options={[
          { value: 'all', label: 'All', count: total },
          { value: 'action', label: 'Needs action', count: groups.action.length },
          { value: 'pending', label: 'Pending', count: groups.pending.length },
          { value: 'scheduled', label: 'Scheduled', count: groups.scheduled.length },
          { value: 'history', label: 'History', count: groups.history.length },
        ]} />
        <label className="search">
          <Icon name="search" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your requests" />
        </label>
      </div>

      {total === 0 && (
        <div className="empty-card">
          <Icon name="sparkle" size={28} />
          <h3>No requests yet</h3>
          <p className="muted">Your first verified expert call is one sentence away.</p>
          <Link to="/new" className="btn btn-primary">Start a request <Icon name="arrow" /></Link>
        </div>
      )}

      {show('action') && groups.action.length > 0 && (
        <Section title="Needs your action" sub="The agent is waiting on you" icon="alert">
          <div className="act-list">
            {groups.action.map((m) => {
              const r = m.req!
              const clar = r.status === 'NEEDS_CLARIFICATION'
              return (
                <div key={m.saved.id} className="act-card spot">
                  <span className="act-icon"><Icon name={clar ? 'help' : 'hand'} size={18} /></span>
                  <div className="grow">
                    <div className="row wrap gap-s"><span className="tag tag-warn">{STATUS_LABEL[r.status]}</span><span className="muted small">{ago(m.saved.created_at, now)}</span></div>
                    <p className="act-q">{clar ? r.clarification_question : r.escalation?.reason}</p>
                    <p className="muted small clamp1">“{m.saved.text}”</p>
                  </div>
                  <Link to={`/requests/${m.saved.id}`} className="btn btn-primary btn-sm" data-cursor={clar ? 'Answer' : 'Approve'}>
                    {clar ? 'Answer' : 'Review & approve'} <Icon name="arrow" size={13} />
                  </Link>
                </div>
              )
            })}
          </div>
        </Section>
      )}

      {show('pending') && (
        <Section title="Pending" sub="Agent is working on these. Hover the stack to spread it" icon="message">
          {groups.pending.length === 0 ? <p className="muted small">Nothing in progress.</p> : (
            <div className="stack" style={{ ['--n' as string]: groups.pending.length }}>
              {groups.pending.map((m, i) => {
                const r = m.req!
                const idx = Math.max(0, STEPS.indexOf(r.status))
                const last = r.timeline[r.timeline.length - 1]
                return (
                  <div key={m.saved.id} className="stack-card spot" style={{ ['--i' as string]: i }}>
                    <div className="row between wrap">
                      <span className="tag tag-live"><span className="live-dot" /> {STATUS_LABEL[r.status]}</span>
                      <span className="mono muted small">{m.saved.id} · {ago(m.saved.created_at, now)}<ChatCount rid={m.saved.id} /></span>
                    </div>
                    <p className="stack-q">“{m.saved.text}”</p>
                    <div className="mini-steps">
                      {STEPS.map((s, k) => <span key={s} className={k < idx ? 'done' : k === idx ? 'on' : ''} title={s} />)}
                    </div>
                    {last && <p className="muted small clamp1"><Icon name={STATUS_ICON[last.step] ?? 'sparkle'} size={13} /> {last.msg}</p>}
                    <div className="row card-actions">
                      <Link to={`/requests/${m.saved.id}`} className="btn btn-ghost btn-sm" data-cursor="Watch">Watch live <Icon name="arrow" size={13} /></Link>
                      <button className="link-btn" onClick={() => remove(m.saved.id)}>Remove from list</button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Section>
      )}

      {show('scheduled') && (
        <Section title="Scheduled" sub="Upcoming calls, soonest first" icon="calendar">
          {groups.scheduled.length === 0 ? <p className="muted small">No upcoming calls.</p> : (
            <div className="sched-grid">
              {groups.scheduled.map((m) => {
                const r = m.req!, b = r.booking!
                const who = r.shortlist.find((s) => s.expert_id === b.expert_id)
                const name = who?.name ?? b.expert_id
                return (
                  <div key={m.saved.id} className="sched-card spot">
                    <div className="sched-left">
                      <span className="sched-day">{day(b.start)}</span>
                      <span className="sched-time">{time(b.start)}</span>
                      <span className="tag tag-ok"><Icon name="clock" size={12} /> {until(b.start, now)}</span>
                    </div>
                    <div className="sched-right">
                      <div className="row"><Avatar name={name} size={34} /><div><div className="strong">{name}</div><div className="muted small">{who?.headline}</div></div></div>
                      <p className="muted small clamp2">“{r.raw_text}”</p>
                      <div className="row wrap gap-s">
                        <span className="fact"><Icon name="clock" size={13} />{time(b.start)} – {time(b.end)}</span>
                        <span className="fact"><Icon name="chart" size={13} />{inr(b.price_inr)}</span>
                      </div>
                      <div className="row wrap card-actions">
                        <a className="btn btn-ghost btn-sm" href={gcalLink(r, name)} target="_blank" rel="noreferrer" data-cursor="Add"><Icon name="calendar" size={13} /> Add to Google Calendar</a>
                        <button className="btn btn-ghost btn-sm" onClick={() => {
                          navigator.clipboard?.writeText(`${name}: ${b.confirmation} (${day(b.start)})`).then(() => { setCopied(m.saved.id); setTimeout(() => setCopied(null), 1400) }).catch(() => {})
                        }}><Icon name={copied === m.saved.id ? 'check' : 'copy'} size={13} /> {copied === m.saved.id ? 'Copied' : 'Copy'}</button>
                        <Link to={`/requests/${m.saved.id}`} className="link-btn">Details</Link>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Section>
      )}

      {show('history') && (
        <Section title="History" sub="Your last 10 finished requests" icon="clock">
          {groups.history.length === 0 ? <p className="muted small">Nothing finished yet.</p> : (
            <div className="hist">
              <div className="hist-row hist-head">
                <span>Request</span><span>Expert</span><span>Price</span><span>Status</span><span />
              </div>
              {groups.history.map((m) => {
                const r = m.req
                const b = r?.booking
                const who = b ? r!.shortlist.find((s) => s.expert_id === b.expert_id)?.name ?? b.expert_id : null
                const ok = r?.status === 'BOOKED'
                return (
                  <div key={m.saved.id} className="hist-row spot">
                    <div className="hist-prompt">
                      <span className="clamp2">“{m.saved.text}”</span>
                      <span className="muted small">{b ? `${day(b.start)}, ${time(b.start)}` : day(m.saved.created_at)} · <span className="mono">{m.saved.id}</span><ChatCount rid={m.saved.id} /></span>
                    </div>
                    <span className="hist-who">{who ? <><Avatar name={who} size={26} /> {who}</> : <span className="muted">—</span>}</span>
                    <span className="mono">{b ? inr(b.price_inr) : '—'}</span>
                    <span>{m.error ? <span className="tag tag-bad">Unavailable</span> : ok ? <span className="tag tag-ok"><Icon name="check" size={12} /> Completed</span> : <span className="tag tag-bad"><Icon name="x" size={12} /> Failed</span>}</span>
                    <span className="hist-actions">
                      {r && <Link to={`/requests/${m.saved.id}`} className="link-btn">View</Link>}
                      <button className="btn btn-ghost btn-sm" onClick={() => again(m.saved.text)} data-cursor="Again">Book again</button>
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </Section>
      )}

      {MOCK && <p className="muted small center dash-note">Mock mode: some entries are samples built from contract fixtures.</p>}
    </div>
  )
}

function ChatCount({ rid }: { rid: string }) {
  const n = listChat(rid).length
  return n ? <span className="chat-count"> · <Icon name="message" size={12} /> {n} {n === 1 ? 'message' : 'messages'}</span> : null
}

function Stat({ icon, n, label, tone = '' }: { icon: 'alert' | 'message' | 'calendar' | 'check' | 'chart'; n: number | string; label: string; tone?: string }) {
  return (
    <div className={`dstat spot ${tone}`}>
      <span className="dstat-icon"><Icon name={icon} size={16} /></span>
      <b>{n}</b>
      <span className="muted small">{label}</span>
    </div>
  )
}

function Section({ title, sub, icon, children }: { title: string; sub: string; icon: 'alert' | 'message' | 'calendar' | 'clock'; children: React.ReactNode }) {
  return (
    <Reveal className="dash-sec">
      <div className="dash-sec-head">
        <span className="opt-icon sm"><Icon name={icon} size={16} /></span>
        <div><h2 className="h2">{title}</h2><p className="muted small">{sub}</p></div>
      </div>
      {children}
    </Reveal>
  )
}
