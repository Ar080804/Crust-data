import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MOCK, googleLoginUrl, ONBOARDING_URL } from '../api.ts'
import { DotField, RotatingText } from '../cursor.tsx'
import { Icon, LinkedInIcon, Logo } from '../ui.tsx'

// Only real identity providers. No email/password, no guest, nothing the user can type to get in.
//  - Client ("I need an expert"): real Google OIDC via the backend (contract "Auth" section).
//  - Expert ("I'm an expert"):   Sunil's onboarding server: LinkedIn OIDC → Telegram → Crustdata check.
type Role = 'client' | 'expert'

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

export default function AuthPage() {
  const loc = useLocation()
  const from = (loc.state as { from?: string } | null)?.from || '/'
  const [role, setRole] = useState<Role | null>(null)

  if (MOCK) return (
    <section className="container">
      <h1>Try Sutradhar</h1>
      <p>This demo uses sample requests and simulated bookings.</p>
      <Link className="btn btn-primary" to="/new">Start a demo request</Link>
    </section>
  )

  const googleLogin = () => { window.location.href = googleLoginUrl(window.location.origin + from) }
  const linkedinLogin = () => { window.location.href = `${ONBOARDING_URL.replace(/\/$/, '')}/auth/linkedin/login` }

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
          {!role ? (
            <>
              <h2 className="auth-title">Welcome to Sutradhar</h2>
              <p className="muted small">How do you want to use Sutradhar?</p>
              <div className="role-grid">
                <button type="button" className="role-card spot" onClick={() => setRole('client')} data-cursor="Client">
                  <span className="opt-icon"><Icon name="search" size={20} /></span>
                  <span className="role-title">I need an expert</span>
                  <span className="muted small">Book a verified expert call in one sentence.</span>
                  <span className="opt-cta">Continue <Icon name="arrow" size={14} /></span>
                </button>
                <button type="button" className="role-card spot" onClick={() => setRole('expert')} data-cursor="Expert">
                  <span className="opt-icon"><Icon name="users" size={20} /></span>
                  <span className="role-title">I'm an expert</span>
                  <span className="muted small">Join the pool, verify your profile, get paid calls.</span>
                  <span className="opt-cta">Continue <Icon name="arrow" size={14} /></span>
                </button>
              </div>
            </>
          ) : (
            <>
              <button type="button" className="back role-back" onClick={() => setRole(null)}><Icon name="back" size={14} /> Back</button>
              {role === 'client' ? (
                <>
                  <h2 className="auth-title">Find your expert</h2>
                  <p className="muted small">Sign in with your Google account to book and track calls.</p>
                  <button type="button" className="btn-oauth role-btn" onClick={googleLogin} data-cursor="Google">
                    <GoogleG /> Continue with Google
                  </button>
                  <ul className="role-points">
                    <li><Icon name="check" size={14} /> Verified identity from Google</li>
                    <li><Icon name="check" size={14} /> Your requests, history and chats in one place</li>
                  </ul>
                </>
              ) : (
                <>
                  <h2 className="auth-title">Join as an expert</h2>
                  <p className="muted small">We verify experts so clients can trust them. It takes about a minute.</p>
                  <button type="button" className="btn-oauth role-btn" onClick={linkedinLogin} disabled={!ONBOARDING_URL} data-cursor="LinkedIn">
                    <LinkedInIcon /> {ONBOARDING_URL ? 'Continue with LinkedIn' : 'Expert onboarding is closed'}
                  </button>
                  <ol className="role-steps">
                    <li><b>Sign in with LinkedIn</b>: confirms who you are</li>
                    <li><b>Link Telegram</b>: that's where clients' requests reach you</li>
                    <li><b>Crustdata check</b>: your profile must match your LinkedIn name</li>
                  </ol>
                </>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  )
}
