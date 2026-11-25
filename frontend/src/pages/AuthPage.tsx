import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { useDemo, ONBOARDING_URL, providerLoginUrl } from '../api.ts'
import { getToken, useUser } from '../auth.ts'
import { DotField, RotatingText } from '../cursor.tsx'
import { GoogleIcon, Icon, LinkedInIcon, Logo } from '../ui.tsx'

const choices = [
  { provider: 'google', label: 'Google', role: 'For users', caption: 'Book and manage your expert calls.', Icon: GoogleIcon },
  { provider: 'linkedin', label: 'LinkedIn', role: 'For experts', caption: 'Connect your professional profile to start verification.', Icon: LinkedInIcon },
] as const

export default function AuthPage() {
  const MOCK = useDemo()
  const { state } = useLocation()
  const [query] = useSearchParams()
  const user = useUser()
  const signedIn = !!getToken() && (user?.provider === 'linkedin' || user?.provider === 'google')
  const expertAccount = signedIn && user?.provider === 'linkedin'
  const wantsUser = query.get('role') === 'user'
  const wantsExpert = query.get('role') === 'expert'
  const showAccount = signedIn && !(expertAccount ? wantsUser : wantsExpert)
  const from = (state as { from?: string } | null)?.from || query.get('next')
  const bookingPage = from?.startsWith('/') && !from.startsWith('//') && !from.includes('\\') ? from : '/new'
  const unavailable = query.get('result') === 'unavailable' ? (wantsUser ? 'google' : wantsExpert ? 'linkedin' : null) : null

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
          {showAccount ? (
            <>
              <h2 className="auth-title">{expertAccount ? 'Expert account' : 'User account'}</h2>
              <p className="muted">Signed in with {expertAccount ? 'LinkedIn' : 'Google'} as {user.name}.</p>
              {expertAccount && (
                <>
                  <p className="auth-status">Your LinkedIn account is connected. Expert onboarding checks your work history with Crustdata.</p>
                  {ONBOARDING_URL && <a className="btn btn-ghost role-btn" href={`${ONBOARDING_URL}/auth/linkedin/login`}><LinkedInIcon /> Continue professional verification</a>}
                </>
              )}
              <Link to={expertAccount ? '/' : bookingPage} className="btn btn-primary role-btn">{expertAccount ? 'Back to home' : 'Continue to booking'}</Link>
            </>
          ) : (
            <>
              <h2 className="auth-title">Log in to Sutradhar</h2>
              {query.get('result') === 'cancelled' && <p role="status" className="auth-status">Sign-in was cancelled. You can try again.</p>}
              <div className="role-grid">
                {choices.map(({ provider, label, role, caption, Icon: ProviderIcon }) => {
                  const content = <><ProviderIcon /> Sign in with {label}</>
                  const next = provider === 'linkedin' ? '/login?role=expert' : bookingPage
                  return (
                    <section key={provider} aria-labelledby={`role-${provider}`} className="login-choice">
                      <h3 id={`role-${provider}`} className="role-title">{role}</h3>
                      <p className="muted small">{caption}</p>
                      <a className="btn-oauth" href={providerLoginUrl(provider, window.location.origin + next)}>{content}</a>
                      {unavailable === provider && (
                        <div className="auth-status" role="alert">
                          <strong>{label} sign-in is unavailable.</strong>
                          <p>Please try again later.</p>
                        </div>
                      )}
                    </section>
                  )
                })}
              </div>
              {MOCK && <Link to="/new" className="auth-demo-link">Try the booking demo <Icon name="arrow" size={14} /></Link>}
            </>
          )}
        </div>
      </section>
    </div>
  )
}
