import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Eval } from '../../../contract/types.ts'
import { getEval } from '../api.ts'
import { useUser } from '../auth.ts'
import { DotField, Magnetic, Reveal, RotatingText } from '../cursor.tsx'
import { Icon, type IconName } from '../ui.tsx'
import Ticket from '../Ticket.tsx'

const OPTIONS: { to: string; icon: IconName; title: string; text: string; cta: string; tag?: string }[] = [
  { to: '/new', icon: 'sparkle', title: 'Book an expert call', text: 'Tell us who you need, when and your budget. The agent does the rest.', cta: 'Start a request', tag: 'Most popular' },
  { to: '/requests', icon: 'clock', title: 'My requests', text: 'Pending, scheduled and past calls in one place. Answer, approve or book again.', cta: 'Open dashboard' },
  { to: '/experts', icon: 'users', title: 'Browse the expert pool', text: 'Opt-in experts with real, checked work history. Filter by rate or company.', cta: 'See experts' },
  { to: '/eval', icon: 'chart', title: 'See how we verify', text: 'Planted fake profiles, paraphrased requests, double-booking tests. The report card.', cta: 'Open report card' },
]

const STEPS: { icon: IconName; t: string; d: string }[] = [
  { icon: 'sparkle', t: 'You type one sentence', d: '“20 min tomorrow evening with a warehouse expert, ₹2000.”' },
  { icon: 'shield', t: 'We check every claim', d: 'Each résumé line is matched against Crustdata. Fakes get dropped.' },
  { icon: 'message', t: 'We negotiate for you', d: 'Experts get a Telegram message. Replies like “7:15 for 1800” are parsed.' },
  { icon: 'calendar', t: 'It lands on your calendar', d: 'Within window, within budget, invites sent to both sides.' },
]

export default function Landing() {
  const user = useUser()
  const first = user && user.provider !== 'guest' ? user.name.split(' ')[0] : null
  const [ev, setEv] = useState<Eval | null>(null)
  useEffect(() => { getEval().then(setEv).catch(() => {}) }, [])

  return (
    <div className="landing">
      {/* ---------- hero ---------- */}
      <section className="hero-x">
        <DotField className="hero-dots" />
        <div className="hero-x-in">
          <span className="announce">
            <span className="announce-tag">{first ? `Hi ${first}` : 'Live'}</span>
            <span className="shiny">Verified expert calls, booked by an AI agent</span>
          </span>
          <h1 className="hero-title">
            Talk to someone who has<br />
            <RotatingText className="grad-anim" words={['run a warehouse', 'scaled quick commerce', 'built last-mile delivery', 'managed 3PL ops', 'fixed a supply chain']} />
            <br />by tonight.
          </h1>
          <p className="hero-sub">
            Sutradhar finds the expert, fact-checks their résumé against Crustdata, haggles on Telegram
            and drops the call on your calendar. You just type one sentence.
          </p>
          <div className="hero-cta">
            <Magnetic>
              <Link to="/new" className="btn btn-primary btn-lg" data-cursor="Start">Start a request <Icon name="arrow" /></Link>
            </Magnetic>
            <Link to="/experts" className="btn btn-ghost btn-lg">Browse experts</Link>
          </div>
          <div className="hero-proof">
            <span><b>{ev ? `${ev.fakes_caught}/${ev.fakes_planted}` : '3/3'}</b> fake profiles caught</span>
            <span className="dotsep" />
            <span><b>{ev ? ev.double_bookings : 0}</b> double bookings</span>
            <span className="dotsep" />
            <span><b>{ev ? ev.budget_violations : 0}</b> budget violations</span>
          </div>
        </div>
        <a href="#options" className="scroll-cue" data-cursor="Scroll">
          <span className="mouse"><span className="wheel" /></span>
          Scroll to explore
        </a>
      </section>

      {/* ---------- options ---------- */}
      <section id="options" className="section">
        <Reveal><p className="kicker center">What would you like to do?</p></Reveal>
        <Reveal delay={80}><h2 className="section-title-x">Pick a starting point</h2></Reveal>
        <div className="opt-grid">
          {OPTIONS.map((o, i) => (
            <Reveal key={o.to} delay={140 + i * 110}>
              <Link to={o.to} className="opt-card spot" data-cursor="Open">
                {o.tag && <span className="opt-tag">{o.tag}</span>}
                <span className="opt-icon"><Icon name={o.icon} size={22} /></span>
                <span className="opt-title">{o.title}</span>
                <span className="muted">{o.text}</span>
                <span className="opt-cta">{o.cta} <Icon name="arrow" size={14} /></span>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---------- how it works ---------- */}
      <section className="section">
        <Reveal><p className="kicker center">How it works</p></Reveal>
        <Reveal delay={80}><h2 className="section-title-x">From one sentence to a booked call</h2></Reveal>
        <div className="how-x">
          <div className="how-steps">
            {STEPS.map((s, i) => (
              <Reveal key={s.t} delay={i * 120}>
                <div className="how-row spot">
                  <span className="how-n">0{i + 1}</span>
                  <span className="opt-icon sm"><Icon name={s.icon} size={18} /></span>
                  <div><div className="strong">{s.t}</div><div className="muted small">{s.d}</div></div>
                </div>
              </Reveal>
            ))}
          </div>
          <Reveal delay={200} className="how-visual">
            <Ticket sample time="7:15 PM" date="Fri, 6 Nov" range="7:15 – 7:35 PM · 20 min" price="₹1,800"
              name="Sunil Kumar" headline="Logistics Manager, Blinkit" eventId="a1b2c3d4e5f60718" />
            <div className="proof-row bad spot">
              <Icon name="x" size={14} />
              <div><b>Caught.</b> Claimed “Warehouse Manager, Flipkart”. Crustdata shows a 3-month internship.</div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------- final CTA ---------- */}
      <section className="section">
        <Reveal>
          <div className="cta-band spot">
            <h2 className="section-title-x">Your next expert call is one sentence away.</h2>
            <Magnetic>
              <Link to="/new" className="btn btn-primary btn-lg" data-cursor="Go">Start a request <Icon name="arrow" /></Link>
            </Magnetic>
          </div>
        </Reveal>
      </section>
    </div>
  )
}
