const TZ = 'Asia/Kolkata'

export const inr = (n: number) => '₹' + n.toLocaleString('en-IN')

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-IN', { timeZone: TZ, hour: 'numeric', minute: '2-digit' })

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-IN', { timeZone: TZ, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })

export function ago(iso: string, now = Date.now()) {
  const s = Math.round((now - +new Date(iso)) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function until(iso: string, now = Date.now()) {
  const s = Math.round((+new Date(iso) - now) / 1000)
  if (s <= 0) return 'now'
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  return d ? `in ${d}d ${h}h` : h ? `in ${h}h ${m}m` : `in ${m}m`
}

export const day = (iso: string) =>
  new Date(iso).toLocaleDateString('en-IN', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short' })
