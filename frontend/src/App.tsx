import { NavLink, Route, Routes } from 'react-router-dom'
import { MOCK } from './api.ts'
import RequestPage from './pages/RequestPage.tsx'
import RequestDetail from './pages/RequestDetail.tsx'
import ExpertsPage from './pages/ExpertsPage.tsx'
import EvalPage from './pages/EvalPage.tsx'

export default function App() {
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">◆ Expert Call Agent</NavLink>
        <nav>
          <NavLink to="/" end>New request</NavLink>
          <NavLink to="/experts">Experts</NavLink>
          <NavLink to="/eval">Eval</NavLink>
        </nav>
        {MOCK && <span className="pill warn" title="Data from contract/fixtures">MOCK DATA</span>}
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<RequestPage />} />
          <Route path="/requests/:id" element={<RequestDetail />} />
          <Route path="/experts" element={<ExpertsPage />} />
          <Route path="/eval" element={<EvalPage />} />
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
      </main>
    </>
  )
}
