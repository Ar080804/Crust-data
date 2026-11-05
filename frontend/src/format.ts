const TZ = 'Asia/Kolkata'

export const inr = (n: number) => '₹' + n.toLocaleString('en-IN')

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-IN', { timeZone: TZ, hour: 'numeric', minute: '2-digit' })

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-IN', { timeZone: TZ, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const day = (iso: string) =>
  new Date(iso).toLocaleDateString('en-IN', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short' })
