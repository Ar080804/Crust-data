import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { getSignInProviders, MOCK, ONBOARDING_URL, providerLoginUrl, type SignInProvider } from '../api.ts'
import { getToken, useUser } from '../auth.ts'
import { DotField, RotatingText } from '../cursor.tsx'
import { GoogleIcon, Icon, LinkedInIcon, Logo } from '../ui.tsx'

export default function AuthPage() {
  const location = useLocation()
  const [query] = useSearchParams()
  const role = query.get('role')
  const provider = role === 'user' ? 'google' : role === 'expert' ? 'telegram' : null
  const expert = provider === 'telegram'
  const label = expert ? 'Telegram' : 'Google'
  const user = useUser()
  const signedIn = !!provider && user?.provider === provider && !!getToken()
  const [availability, setAvailability] = useState<Record<SignInProvider, boolean> | 'error' | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!provider || signedIn) return
    const controller = new AbortController()
    getSignInProviders(controller.signal)
      .then((providers) => { if (!controller.signal.aborted) setAvailability(providers) })
      .catch(() => { if (!controller.signal.aborted) setAvailability('error') })
    return () => controller.abort()
  }, [provider, signedIn, attempt])

  const from = (location.state as { from?: string } | null)?.from
  const next = !expert && from?.startsWith('/') && !from.startsWith('//') ? from : expert ? '/login?role=expert' : '/new'
  const ready = provider && availability && availability !== 'error' && availability[provider]

  return (
    <div className="auth">
      <section className="auth-art">
        <DotField />
        <div className="auth-art-in">
          <Link to="/" className="brand"><Logo size={30} /><span className="brand-word">Sutradhar</span></Link>
          <h1 className="auth-line">The right expert<br />is already out there.<br />
            <span className="muted-line">We make sure they're</span>{' '}
            <RotatingText className="grad-anim" words={['real.', 'verified.', 'available.', 'on budget.']} />
          </h1>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <Link className="back role-back" to="/"><Icon name="back" size={14} /> Home</Link>
          {!provider ? (
            <>
              <h2 className="auth-title">Sign in to Sutradhar</h2>
              <div className="role-grid">
                <Link className="role-card" to="/login?role=user" state={location.state}>
                  <GoogleIcon /><span className="role-title">I need an expert</span><span>Sign in with Google</span>
                </Link>
                <Link className="role-card" to="/login?role=expert">
                  <Icon name="send" /><span className="role-title">I'm an expert</span><span>Sign in with Telegram</span>
                </Link>
              </div>
            </>
          ) : signedIn ? (
            <>
              <h2 className="auth-title">{expert ? 'Expert account' : 'User account'}</h2>
              <p className="muted">Signed in with {label} as {user.name}.</p>
              {expert && <p className="auth-status">Professional verification and booking availability are managed through expert onboarding.</p>}
              {expert && ONBOARDING_URL && <a className="btn btn-ghost role-btn" href={`${ONBOARDING_URL}/auth/linkedin/login`}><LinkedInIcon /> Verify professional profile</a>}
              <Link to={expert ? '/' : next} className="btn btn-primary role-btn">{expert ? 'Back to home' : 'Continue to booking'}</Link>
            </>
          ) : (
            <>
              <h2 className="auth-title">{expert ? 'Expert sign-in' : 'User sign-in'}</h2>
              <p className="muted">{expert ? 'Use Telegram to identify yourself as an expert.' : 'Use Google to sign in and manage your booking requests.'}</p>
              {query.get('result') === 'cancelled' && <p role="status" className="auth-status">Sign-in was cancelled. You can try again.</p>}
              {ready ? (
                <a className="btn-oauth role-btn" href={providerLoginUrl(provider, window.location.origin + next)}>
                  {expert ? <Icon name="send" /> : <GoogleIcon />} Continue with {label}
                </a>
              ) : (
                <>
                  <button type="button" className="btn-oauth role-btn" disabled aria-describedby="provider-status">
                    {expert ? <Icon name="send" /> : <GoogleIcon />} Continue with {label}
                  </button>
                  <p id="provider-status" className="auth-status" role="status">{availability === null ? 'Checking sign-in availability…'
                    : availability === 'error' ? 'Could not check sign-in availability.' : `${label} sign-in is awaiting setup on this site.`}</p>
                  {availability === 'error' && <button type="button" className="link-btn" onClick={() => { setAvailability(null); setAttempt((count) => count + 1) }}>Check again</button>}
                </>
              )}
              {expert && ONBOARDING_URL && <a className="expert-join inline" href={`${ONBOARDING_URL}/auth/linkedin/login`}><LinkedInIcon size={16} /> Join with LinkedIn and link Telegram</a>}
              {MOCK && <Link to="/new" className="btn btn-ghost role-btn">Try the booking demo <Icon name="arrow" size={14} /></Link>}
              <Link to="/login" state={location.state} className="auth-switch">Choose another sign-in option</Link>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
