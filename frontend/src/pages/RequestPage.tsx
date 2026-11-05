import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createRequest } from '../api.ts'

const EXAMPLE = 'Need a 20 min call tomorrow evening 6-8 with someone who has managed a warehouse, budget 2000'

export default function RequestPage() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const nav = useNavigate()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true); setErr(null)
    try {
      const { request_id } = await createRequest(text.trim())
      nav(`/requests/${request_id}`)
    } catch (ex) {
      setErr((ex as Error).message)
      setBusy(false)
    }
  }

  return (
    <section className="hero">
      <h1>Book an expert call, in one sentence.</h1>
      <p className="muted">
        Say who you need, when, and your budget. The agent finds experts, checks their claims against Crustdata,
        negotiates on Telegram and books the calendar slot.
      </p>
      <form onSubmit={submit} className="card">
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={EXAMPLE}
          autoFocus
        />
        <div className="row between">
          <button type="button" className="link" onClick={() => setText(EXAMPLE)}>Use example</button>
          <button type="submit" disabled={busy || !text.trim()}>{busy ? 'Submitting…' : 'Submit'}</button>
        </div>
        {err && <p className="error">⚠ {err}</p>}
      </form>
    </section>
  )
}
