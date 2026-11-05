// Cursor-reactive effects, zero dependencies.
import { useEffect, useRef, useState } from 'react'

/* Custom cursor: exact dot + lagging ring + big soft glow. Ring grows over clickable things
   and shows a label from data-cursor="...". Only on mouse/trackpad devices. */
export function CursorFX() {
  const dot = useRef<HTMLDivElement>(null)
  const ring = useRef<HTMLDivElement>(null)
  const glow = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!window.matchMedia?.('(pointer: fine)').matches) return
    const root = document.documentElement
    root.classList.add('has-cursor')
    let x = innerWidth / 2, y = innerHeight / 2, rx = x, ry = y, gx = x, gy = y, raf = 0
    const move = (e: PointerEvent) => {
      x = e.clientX; y = e.clientY
      const t = (e.target as HTMLElement | null)?.closest?.('a,button,input,textarea,select,label,[data-cursor]') as HTMLElement | null
      const r = ring.current!
      r.classList.toggle('hover', !!t)
      r.classList.toggle('text', !!t && /^(INPUT|TEXTAREA)$/.test(t.tagName))
      r.dataset.label = t?.getAttribute('data-cursor') ?? ''
      root.classList.remove('cursor-hidden')
    }
    const down = () => ring.current?.classList.add('down')
    const up = () => ring.current?.classList.remove('down')
    const out = (e: MouseEvent) => { if (!e.relatedTarget) root.classList.add('cursor-hidden') }
    const loop = () => {
      rx += (x - rx) * 0.2; ry += (y - ry) * 0.2
      gx += (x - gx) * 0.07; gy += (y - gy) * 0.07
      if (dot.current) dot.current.style.transform = `translate3d(${x}px, ${y}px, 0)`
      if (ring.current) ring.current.style.transform = `translate3d(${rx}px, ${ry}px, 0)`
      if (glow.current) glow.current.style.transform = `translate3d(${gx}px, ${gy}px, 0)`
      raf = requestAnimationFrame(loop)
    }
    addEventListener('pointermove', move, { passive: true })
    addEventListener('pointerdown', down)
    addEventListener('pointerup', up)
    document.addEventListener('mouseout', out)
    raf = requestAnimationFrame(loop)
    return () => {
      root.classList.remove('has-cursor')
      removeEventListener('pointermove', move); removeEventListener('pointerdown', down); removeEventListener('pointerup', up)
      document.removeEventListener('mouseout', out)
      cancelAnimationFrame(raf)
    }
  }, [])
  return (
    <>
      <div className="cursor-glow" ref={glow} aria-hidden />
      <div className="cursor-ring" ref={ring} aria-hidden />
      <div className="cursor-dot" ref={dot} aria-hidden />
    </>
  )
}

/* DotField: a grid of dots that breathes on its own and gets pushed + lit by the cursor. */
export function DotField({ gap = 26, radius = 150, className = '' }: { gap?: number; radius?: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current!
    const ctx = cv.getContext('2d')!
    let w = 0, h = 0, raf = 0, visible = true
    let mx = -9999, my = -9999
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const css = getComputedStyle(document.documentElement)
    const fit = () => {
      const r = cv.getBoundingClientRect()
      w = r.width; h = r.height
      cv.width = w * dpr; cv.height = h * dpr
    }
    const onMove = (e: PointerEvent) => {
      const r = cv.getBoundingClientRect()
      mx = e.clientX - r.left; my = e.clientY - r.top
    }
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw)
      if (!visible) return
      const accent = css.getPropertyValue('--accent').trim() || '#8183ff'
      const base = css.getPropertyValue('--line-2').trim() || 'rgba(255,255,255,.14)'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      for (let y = gap / 2; y < h; y += gap) {
        for (let x = gap / 2; x < w; x += gap) {
          const dx = x - mx, dy = y - my
          const d = Math.hypot(dx, dy)
          const wave = Math.sin(t / 900 + (x + y) / 140) * 0.5 + 0.5
          let px = x, py = y, s = 1 + wave * 0.5
          if (d < radius) {
            const f = 1 - d / radius
            px += (dx / (d || 1)) * f * 16
            py += (dy / (d || 1)) * f * 16
            s += f * 2.2
            ctx.fillStyle = accent
            ctx.globalAlpha = 0.25 + f * 0.75
          } else {
            ctx.fillStyle = base
            ctx.globalAlpha = 0.5 + wave * 0.5
          }
          ctx.beginPath(); ctx.arc(px, py, s, 0, Math.PI * 2); ctx.fill()
        }
      }
      ctx.globalAlpha = 1
    }
    fit()
    const ro = new ResizeObserver(fit); ro.observe(cv)
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting }); io.observe(cv)
    addEventListener('pointermove', onMove, { passive: true })
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); removeEventListener('pointermove', onMove) }
  }, [gap, radius])
  return <canvas ref={ref} className={`dotfield ${className}`} aria-hidden />
}

/* Magnetic: children drift toward the cursor while hovered. */
export function Magnetic({ children, strength = 0.3 }: { children: React.ReactNode; strength?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  return (
    <span ref={ref} className="magnetic"
      onMouseMove={(e) => {
        const el = ref.current!; const r = el.getBoundingClientRect()
        el.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * strength}px, ${(e.clientY - r.top - r.height / 2) * strength}px)`
      }}
      onMouseLeave={() => { ref.current!.style.transform = '' }}>
      {children}
    </span>
  )
}

/* Reveal: fades/slides children in when scrolled into view. */
export function Reveal({ children, delay = 0, className = '' }: {
  children: React.ReactNode; delay?: number; className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current!
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect() } }, { threshold: 0.15 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return <div ref={ref} className={`reveal ${shown ? 'in' : ''} ${className}`} style={{ transitionDelay: `${delay}ms` }}>{children}</div>
}

/* RotatingText: cycles through words with a slide-up. */
export function RotatingText({ words, ms = 2200, className = '' }: { words: string[]; ms?: number; className?: string }) {
  const [i, setI] = useState(0)
  useEffect(() => { const id = setInterval(() => setI((n) => (n + 1) % words.length), ms); return () => clearInterval(id) }, [words.length, ms])
  return (
    <span className={`rotator ${className}`}>
      <span key={i} className="rotator-word">{words[i]}</span>
    </span>
  )
}
