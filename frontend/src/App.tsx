import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { MOCK } from './api.ts'
import { Avatar, Icon, Logo } from './ui.tsx'
import { Aurora, ClickSpark, useSpotlight } from './effects.tsx'
import { CursorFX } from './cursor.tsx'
import { getToken, getUser, setToken, signIn, signOut, useUser } from './auth.ts'
import { getMe, logout } from './api.ts'
import AuthPage from './pages/AuthPage.tsx'
import Landing from './pages/Landing.tsx'
import RequestPage from './pages/RequestPage.tsx'
import RequestDetail from './pages/RequestDetail.tsx'
import MyRequests from './pages/MyRequests.tsx'
import ExpertsPage from './pages/ExpertsPage.tsx'
import EvalPage from './pages/EvalPage.tsx'

type Theme = 'light' | 'dark'
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* storage blocked */ }
  return 'dark'
}

// The sample wizard is public. Live booking requires a Google client session.
function RequireAuth({ children }: { children: React.ReactElement }) {
  const user = useUser()
  const loc = useLocation()
  const verified = !!user && user.provider === 'google' && !!getToken()
  if (!MOCK && !verified) return <Navigate to="/login?role=user" replace state={{ from: loc.pathname + loc.search }} />
  return children
}

// After provider sign-in the backend redirects to "<page>#session=<token>" (contract: Auth section).
const sessionInHash = () => new URLSearchParams(window.location.hash.slice(1)).get('session')

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const user = useUser()
  const loc = useLocation()
  const nav = useNavigate()
  const authScreen = loc.pathname === '/login'
  const [callbackToken] = useState(sessionInHash)
  const [booting, setBooting] = useState(!!callbackToken)
  const [authErr, setAuthErr] = useState<string | null>(null)

  // Drop retired login types while preserving current Google and LinkedIn sessions.
  useEffect(() => {
    if (sessionInHash()) return
    const u = getUser()
    if (u && (!['google', 'linkedin'].includes(u.provider) || !getToken())) signOut()
  }, [])

  useEffect(() => {
    if (!callbackToken) return
    let active = true
    history.replaceState(null, '', window.location.pathname + window.location.search) // clear the hash
    getMe(callbackToken)
      .then((me) => {
        if (!active) return
        setToken(callbackToken)
        signIn(me)
      })
      .catch((e) => { if (active) { signOut(); setAuthErr(`Sign-in failed: ${(e as Error).message}`) } })
      .finally(() => { if (active) setBooting(false) })
    return () => { active = false }
  }, [callbackToken])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('theme', theme) } catch { /* ignore */ }
  }, [theme])
  useEffect(() => { window.scrollTo(0, 0) }, [loc.pathname])
  useSpotlight()

  return (
    <>
      <CursorFX />
      {!authScreen && <Aurora />}
      <ClickSpark color={theme === 'dark' ? '#a5a6ff' : '#5e6ad2'} />

      {!authScreen && (
        <header className="topbar">
          <div className="topbar-in">
            <NavLink to="/" className="brand"><Logo /> <span>Sutradhar</span></NavLink>
            <nav>
              <NavLink to="/" end>Home</NavLink>
              <NavLink to="/new">New request</NavLink>
              <NavLink to="/requests" end>My requests</NavLink>
              <NavLink to="/experts">Experts</NavLink>
              <NavLink to="/eval">Eval</NavLink>
            </nav>
            <div className="row">
              {MOCK && <span className="tag tag-warn" title="Sample requests with simulated Telegram replies and calendar bookings">Mock data</span>}
              <button className="icon-btn" aria-label="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
                <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
              </button>
              {user ? (
                <div className="user-chip">
                  <Avatar name={user.name} size={28} />
                  {user.provider === 'linkedin'
                    ? <NavLink to="/login?role=expert" className="user-name">Expert account</NavLink>
                    : <span className="user-name">{user.name}</span>}
                  <button className="link-btn" onClick={() => { const t = getToken(); if (t) logout(t); signOut(); nav('/login') }}>Sign out</button>
                </div>
              ) : (
                <NavLink to="/login" className="btn btn-primary btn-sm">Login</NavLink>
              )}
            </div>
          </div>
        </header>
      )}

      <main className={authScreen ? '' : 'container'}>
        {authErr && <div className="banner bad">{authErr}</div>}
        {booting ? <div className="loading"><span className="spinner" /> Signing you in…</div> : (
        <Routes>
          <Route path="/login" element={<AuthPage />} />
          <Route path="/" element={<Landing />} />
          <Route path="/new" element={<RequireAuth><RequestPage /></RequireAuth>} />
          <Route path="/requests" element={<RequireAuth><MyRequests /></RequireAuth>} />
          <Route path="/requests/:id" element={<RequestDetail />} />
          <Route path="/experts" element={<ExpertsPage />} />
          <Route path="/eval" element={<EvalPage />} />
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
        )}
      </main>

      {!authScreen && (
        <footer className="foot">
          Sutradhar · claims verified with Crustdata · negotiated on Telegram · booked on Google Calendar
        </footer>
      )}
    </>
  )
}
