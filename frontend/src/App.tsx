import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { MOCK } from './api.ts'
import { Avatar, Icon, Logo } from './ui.tsx'
import { Aurora, ClickSpark, useSpotlight } from './effects.tsx'
import { CursorFX } from './cursor.tsx'
import { getToken, setToken, signIn, signOut, useUser } from './auth.ts'
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

// Only the landing page and the request wizard ask for login. Detail / experts / eval stay open,
// so teammates can open /requests/<id> directly while testing the backend.
function RequireAuth({ children }: { children: React.ReactElement }) {
  const user = useUser()
  const loc = useLocation()
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  return children
}

// After real Google sign-in the backend redirects to "<page>#session=<token>" (contract: Auth section).
const sessionInHash = () => new URLSearchParams(window.location.hash.slice(1)).get('session')

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const user = useUser()
  const loc = useLocation()
  const nav = useNavigate()
  const authScreen = loc.pathname === '/login'
  const [booting, setBooting] = useState(() => !!sessionInHash())
  const [authErr, setAuthErr] = useState<string | null>(null)

  useEffect(() => {
    const token = sessionInHash()
    if (!token) return
    history.replaceState(null, '', window.location.pathname + window.location.search) // clear the hash
    setToken(token)
    getMe(token)
      .then((me) => signIn({ name: me.name || me.email, email: me.email, provider: 'google', picture: me.picture }))
      .catch((e) => { setToken(null); setAuthErr(`Google sign-in failed: ${(e as Error).message}`) })
      .finally(() => setBooting(false))
  }, [])
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
              {MOCK && <span className="tag tag-warn" title="Reading contract/fixtures, not the backend">Mock data</span>}
              <button className="icon-btn" aria-label="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
                <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
              </button>
              {user ? (
                <div className="user-chip">
                  <Avatar name={user.name} size={28} />
                  <span className="user-name">{user.name}</span>
                  <button className="link-btn" onClick={() => { const t = getToken(); if (t) logout(t); signOut(); nav('/login') }}>Sign out</button>
                </div>
              ) : (
                <NavLink to="/login" className="btn btn-primary btn-sm">Log in</NavLink>
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
          <Route path="/" element={<RequireAuth><Landing /></RequireAuth>} />
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
