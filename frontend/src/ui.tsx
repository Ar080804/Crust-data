// Presentational helpers only. No data fetching here.
import { useEffect, useState } from 'react'

/* ---------- icons (lucide-style, 24px grid, stroke) ---------- */
const P: Record<string, React.ReactNode> = {
  check: <path d="M20 6 9 17l-5-5" />,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  arrow: <path d="M5 12h14M12 5l7 7-7 7" />,
  back: <path d="M19 12H5M12 19l-7-7 7-7" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>,
  shield: <><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" /><path d="m9 12 2 2 4-4" /></>,
  send: <path d="M22 2 11 13M22 2l-7 20-4-9-9-4z" />,
  message: <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z" />,
  calendar: <><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
  alert: <><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z" /><path d="M12 9v4M12 17h.01" /></>,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01" /></>,
  sparkle: <path d="M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6zM19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7z" />,
  copy: <><rect x="8" y="8" width="13" height="13" rx="2" /><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4" /></>,
  moon: <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z" />,
  external: <path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />,
  chart: <path d="M3 3v18h18M18 17V9M13 17V5M8 17v-3" />,
  hand: <path d="M18 11V6a2 2 0 0 0-4 0M14 10V4a2 2 0 0 0-4 0v2M10 10.5V6a2 2 0 0 0-4 0v8M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.9-6-2.3l-3.6-3.6a2 2 0 0 1 2.8-2.8L7 15" />,
  code: <path d="m16 18 6-6-6-6M8 6l-6 6 6 6" />,
  database: <><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14a9 3 0 0 0 18 0V5M3 12a9 3 0 0 0 18 0" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  link: <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" />,
}
export type IconName = keyof typeof P
export function Icon({ name, size = 16, className = '' }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {P[name]}
    </svg>
  )
}

export const STATUS_ICON: Record<string, IconName> = {
  INTAKE: 'sparkle', FINDING: 'search', VERIFYING: 'shield', OUTREACH: 'send', NEGOTIATING: 'message',
  BOOKING: 'calendar', BOOKED: 'check', NEEDS_CLARIFICATION: 'help', ESCALATED: 'hand', FAILED: 'x',
}
export const SOURCE_ICON: Record<string, IconName> = {
  llm: 'sparkle', code: 'code', crustdata: 'database', telegram: 'send', gcal: 'calendar', human: 'hand',
}
export const STATUS_LABEL: Record<string, string> = {
  INTAKE: 'Understanding request', NEEDS_CLARIFICATION: 'Needs your input', FINDING: 'Finding experts',
  VERIFYING: 'Verifying claims', OUTREACH: 'Reaching out', NEGOTIATING: 'Negotiating', BOOKING: 'Booking calendar',
  BOOKED: 'Booked', ESCALATED: 'Needs approval', FAILED: 'Failed',
}

/* ---------- avatar ---------- */
const HUES = [18, 38, 152, 200, 232, 280, 330]
export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const clean = name.replace(/["“”]/g, '')
  const initials = clean.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  let h = 0
  for (const ch of clean) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  const hue = HUES[h % HUES.length]
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.36, ['--h' as string]: hue }}>
      {initials || '?'}
    </span>
  )
}

/* ---------- misc ---------- */
export function useCountUp(target: number, ms = 900) {
  const [v, setV] = useState(0)
  useEffect(() => {
    let raf = 0
    const t0 = performance.now()
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / ms)
      setV(Math.round(target * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}

export function Segmented<T extends string>({ value, options, onChange }: {
  value: T; options: { value: T; label: string; count?: number }[]; onChange: (v: T) => void
}) {
  return (
    <div className="seg" role="tablist">
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={value === o.value}
          className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}{o.count !== undefined && <span className="cnt">{o.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Confetti() {
  const colors = ['var(--accent)', 'var(--ok)', 'var(--ink)', '#e9b949', '#7c83db']
  return (
    <div className="confetti" aria-hidden>
      {Array.from({ length: 22 }, (_, i) => (
        <i key={i} style={{ left: `${(i * 41) % 100}%`, background: colors[i % colors.length], animationDelay: `${(i % 6) * 0.1}s` }} />
      ))}
    </div>
  )
}

export function Logo({ size = 26 }: { size?: number }) {
  // A thread knotted through three beads: the sutradhar holding the strings.
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="logo">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8b8dff" /><stop offset="1" stopColor="#5e6ad2" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#lg)" />
      <path d="M5 21c4-9 7-9 11 0s7 9 11 0" fill="none" stroke="#fff" strokeOpacity=".55" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="9" cy="15.5" r="2.3" fill="#fff" />
      <circle cx="16" cy="21" r="2.3" fill="#fff" />
      <circle cx="23" cy="15.5" r="2.3" fill="#fff" />
    </svg>
  )
}
