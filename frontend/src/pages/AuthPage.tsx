import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { signIn, nameFromEmail } from '../auth.ts'
import { REAL_GOOGLE, googleLoginUrl } from '../api.ts'
import { DotField, RotatingText } from '../cursor.tsx'
import { Icon, Logo, Segmented } from '../ui.tsx'

type Mode = 'login' | 'signup'
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

function GoogleG() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  )
}

function LinkedInIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <rect width="24" height="24" rx="4" fill="#0A66C2" />
      <path fill="#fff" d="M7.1 9.5H4.6V19h2.5V9.5zM5.9 5.2a1.45 1.45 0 1 0 0 2.9 1.45 1.45 0 0 0 0-2.9zM19.4 13.6c0-2.6-1.4-4.3-3.6-4.3-1.3 0-2.1.7-2.5 1.3V9.5h-2.4V19h2.5v-4.9c0-1.3.4-2.4 1.8-2.4 1.3 0 1.7 1.1 1.7 2.5V19h2.5v-5.4z" />
    </svg>
  )
}

export default function AuthPage() {
  const nav = useNavigate()
  const loc = useLocation()
  const from = (loc.state as { from?: string } | null)?.from || '/'
  const [mode, setMode] = useState<Mode>('signup')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [oauth, setOauth] = useState<null | 'google' | 'linkedin'>(null)
  const [gmail, setGmail] = useState('')

  const done = () => nav(from, { replace: true })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (mode === 'signup' && !name.trim()) return setErr('Please enter your name.')
    if (!EMAIL_RE.test(email.trim())) return setErr('That email does not look right.')
    if (pw.length < 6) return setErr('Password needs at least 6 characters.')
    signIn({ name: name.trim() || nameFromEmail(email), email: email.trim(), provider: 'email' })
    done()
  }

  function oauthContinue(e: React.FormEvent) {
    e.preventDefault()
    if (!EMAIL_RE.test(gmail.trim())) return setErr(`Enter your ${oauth === 'linkedin' ? 'LinkedIn' : 'Google'} email.`)
    signIn({ name: nameFromEmail(gmail), email: gmail.trim(), provider: oauth ?? 'google' })
    done()
  }

  function startGoogle() {
    setErr(null)
    // Real backend: real Google OIDC (contract "Auth" section). Mock: demo account picker.
    if (REAL_GOOGLE) window.location.href = googleLoginUrl(window.location.origin + from)
    else setOauth('google')
  }

  return (
    <div className="auth">
      <section className="auth-art">
        <DotField />
        <div className="auth-art-in">
          <div className="row"><Logo size={30} /><span className="brand-word">Sutradhar</span></div>
          <h1 className="auth-line">
            The right expert<br />is already out there.<br />
            <span className="muted-line">We make sure they're</span>{' '}
            <RotatingText className="grad-anim" words={['real.', 'verified.', 'available.', 'on budget.']} />
          </h1>
          <ul className="auth-points">
            <li><Icon name="shield" size={16} /> Every work-history claim checked against Crustdata</li>
            <li><Icon name="message" size={16} /> Negotiated live on Telegram, in seconds</li>
            <li><Icon name="calendar" size={16} /> Lands straight on your Google Calendar</li>
          </ul>
          <p className="auth-hint">Move your cursor around ✦</p>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <h2 className="auth-title">{mode === 'signup' ? 'Create your account' : 'Welcome back'}</h2>
          <p className="muted small">{mode === 'signup' ? 'Book your first verified expert call in under a minute.' : 'Log in to continue to your requests.'}</p>

          <div className="auth-tabs">
            <Segmented value={mode} onChange={(m) => { setMode(m); setErr(null) }} options={[
              { value: 'signup', label: 'Sign up' }, { value: 'login', label: 'Log in' },
            ]} />
          </div>

          {!oauth ? (
            <div className="oauth-row">
              <button type="button" className="btn-oauth" onClick={startGoogle} data-cursor="Google">
                <GoogleG /> Google
              </button>
              <button type="button" className="btn-oauth" onClick={() => { setOauth('linkedin'); setErr(null) }} data-cursor="LinkedIn">
                <LinkedInIcon /> LinkedIn
              </button>
            </div>
          ) : (
            <form className="oauth-box" onSubmit={oauthContinue}>
              <div className="row">
                {oauth === 'google' ? <GoogleG /> : <LinkedInIcon />}
                <span className="strong">{oauth === 'google' ? 'Choose a Google account' : 'Sign in with LinkedIn'}</span>
              </div>
              <input type="email" value={gmail} onChange={(e) => setGmail(e.target.value)}
                placeholder={oauth === 'google' ? 'you@gmail.com' : 'Email on your LinkedIn'} autoFocus />
              <div className="row">
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOauth(null)}>Cancel</button>
                <button className="btn btn-primary btn-sm">Continue</button>
              </div>
            </form>
          )}

          <div className="divider"><span>or with email</span></div>

          <form onSubmit={submit} className="auth-form">
            {mode === 'signup' && (
              <label className="field"><span>Full name</span>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Deepak Chauhan" autoComplete="name" />
              </label>
            )}
            <label className="field"><span>Email</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
            </label>
            <label className="field"><span>Password</span>
              <div className="pw">
                <input type={showPw ? 'text' : 'password'} value={pw} onChange={(e) => setPw(e.target.value)} placeholder="At least 6 characters"
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} />
                <button type="button" className="pw-toggle" onClick={() => setShowPw(!showPw)}>{showPw ? 'Hide' : 'Show'}</button>
              </div>
            </label>
            {err && <p className="error"><Icon name="alert" /> {err}</p>}
            <button className="btn btn-primary btn-block" data-cursor="Go">
              {mode === 'signup' ? 'Create account' : 'Log in'} <Icon name="arrow" />
            </button>
          </form>

          <button type="button" className="guest" onClick={() => { signIn({ name: 'Guest', email: '', provider: 'guest' }); done() }}>
            Skip for now, continue as guest
          </button>
          <p className="auth-note">Demo build: your account is stored only in this browser.</p>
        </div>
      </section>
    </div>
  )
}
