// Animation effects in the spirit of reactbits.dev, written in-house with zero dependencies
// (so package.json stays untouched). Purely visual: no data logic here.
import { useEffect, useRef, useState } from 'react'

/* BlurText: words fade in from a blur, one after another. '\n' = line break. */
type Part = string | { t: string; cls: string }
export function BlurText({ parts, className = '', step = 70, as: Tag = 'h1' }: {
  parts: Part[]; className?: string; step?: number; as?: 'h1' | 'h2' | 'p'
}) {
  let i = 0
  return (
    <Tag className={className}>
      {parts.map((p, pi) => {
        if (p === '\n') return <br key={pi} />
        const text = typeof p === 'string' ? p : p.t
        const cls = typeof p === 'string' ? '' : p.cls
        return (
          <span key={pi}>
            {text.split(' ').filter(Boolean).map((w, wi) => (
              <span key={wi} className={`blur-word ${cls}`} style={{ animationDelay: `${i++ * step}ms` }}>{w}&nbsp;</span>
            ))}
          </span>
        )
      })}
    </Tag>
  )
}

/* ShinyText: a light sweep across muted text. */
export function ShinyText({ text, className = '' }: { text: string; className?: string }) {
  return <span className={`shiny ${className}`}>{text}</span>
}

/* DecryptedText: scrambles, then resolves left to right. */
const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#%&*+<>/'
export function DecryptedText({ text, ms = 1100, className = '' }: { text: string; ms?: number; className?: string }) {
  const [out, setOut] = useState(text)
  useEffect(() => {
    let raf = 0
    const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / ms)
      const n = Math.floor(p * text.length)
      let s = text.slice(0, n)
      for (let k = n; k < text.length; k++) s += text[k] === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0]
      setOut(s)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [text, ms])
  return <span className={`decrypt ${className}`} aria-label={text}>{out}</span>
}

/* SpotlightCard: any element with class "spot" gets a glow that follows the cursor. */
export function useSpotlight() {
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const el = (e.target as HTMLElement | null)?.closest?.('.spot') as HTMLElement | null
      if (!el) return
      const r = el.getBoundingClientRect()
      el.style.setProperty('--mx', `${e.clientX - r.left}px`)
      el.style.setProperty('--my', `${e.clientY - r.top}px`)
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => window.removeEventListener('pointermove', onMove)
  }, [])
}

/* ClickSpark: small sparks burst out wherever you click. */
export function ClickSpark({ color = '#a5a6ff' }: { color?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current!
    const ctx = cv.getContext('2d')!
    let sparks: { x: number; y: number; a: number; t0: number }[] = []
    let raf = 0
    const fit = () => { cv.width = innerWidth * devicePixelRatio; cv.height = innerHeight * devicePixelRatio }
    fit()
    const draw = (now: number) => {
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
      ctx.clearRect(0, 0, innerWidth, innerHeight)
      sparks = sparks.filter((s) => now - s.t0 < 450)
      for (const s of sparks) {
        const p = (now - s.t0) / 450
        const e = 1 - Math.pow(1 - p, 3)
        const d1 = 6 + e * 22, len = 9 * (1 - p)
        ctx.strokeStyle = color; ctx.globalAlpha = 1 - p; ctx.lineWidth = 2; ctx.lineCap = 'round'
        ctx.beginPath()
        ctx.moveTo(s.x + Math.cos(s.a) * d1, s.y + Math.sin(s.a) * d1)
        ctx.lineTo(s.x + Math.cos(s.a) * (d1 + len), s.y + Math.sin(s.a) * (d1 + len))
        ctx.stroke()
      }
      raf = sparks.length ? requestAnimationFrame(draw) : 0
    }
    const onClick = (e: MouseEvent) => {
      const t0 = performance.now()
      for (let k = 0; k < 8; k++) sparks.push({ x: e.clientX, y: e.clientY, a: (Math.PI * 2 * k) / 8, t0 })
      if (!raf) raf = requestAnimationFrame(draw)
    }
    addEventListener('click', onClick)
    addEventListener('resize', fit)
    return () => { removeEventListener('click', onClick); removeEventListener('resize', fit); cancelAnimationFrame(raf) }
  }, [color])
  return <canvas ref={ref} className="click-spark" aria-hidden />
}

/* Aurora: soft moving light at the top of the page. */
export function Aurora() {
  return (
    <div className="aurora" aria-hidden>
      <span className="a1" /><span className="a2" /><span className="a3" />
      <div className="grid-fade" />
    </div>
  )
}
