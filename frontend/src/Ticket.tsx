import { useState } from 'react'
import { Avatar, Icon } from './ui.tsx'

export interface TicketProps {
  time: string        // "7:15 PM"
  date: string        // "Fri, 6 Nov"
  range: string       // "7:15 – 7:35 PM"
  price: string       // "₹1,800"
  name: string
  headline?: string
  eventId: string
  confirmation?: string
  sample?: boolean
  simulated?: boolean
}

export default function Ticket(p: TicketProps) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard?.writeText(`${p.name}: ${p.confirmation ?? `${p.time}, ${p.price}`} (${p.date})`)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400) }).catch(() => {})
  }
  return (
    <div className={`ticket ${p.sample ? 'sample' : ''}`}>
      <div className="ticket-main">
        <div className="ticket-top">
          <span className="ticket-kicker"><Icon name="check" size={14} /> {p.sample || p.simulated ? 'Sample booking' : 'Call confirmed'}</span>
          <span className="mono muted small">{p.date}</span>
        </div>
        <div className="ticket-time">{p.time}</div>
        <div className="ticket-sub">{p.range}</div>
        <div className="ticket-who">
          <Avatar name={p.name} size={34} />
          <div>
            <div className="strong">{p.name}</div>
            {p.headline && <div className="muted small">{p.headline}</div>}
          </div>
        </div>
      </div>
      <div className="ticket-stub">
        <div className="stub-label">Price</div>
        <div className="ticket-price">{p.price}</div>
        <div className="stub-label">Invite</div>
        <div className="small"><Icon name="calendar" size={13} /> {p.sample || p.simulated ? 'Simulated' : 'Sent to both'}</div>
        <div className="stub-label">Event</div>
        <div className="mono small ellip">{p.eventId}</div>
        {!p.sample && (
          <button type="button" className="btn btn-ghost btn-sm stub-btn" onClick={copy}>
            <Icon name={copied ? 'check' : 'copy'} size={13} /> {copied ? 'Copied' : 'Copy'}
          </button>
        )}
      </div>
    </div>
  )
}
