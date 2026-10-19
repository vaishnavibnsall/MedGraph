import { NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Leaderboard from './pages/Leaderboard'
import NetworkPage from './pages/NetworkPage'
import Compliance from './pages/Compliance'
import PhysicianPage from './pages/PhysicianPage'

const nav = [
  { to: '/', label: 'Overview', end: true },
  { to: '/leaderboard', label: 'KOL Leaderboard' },
  { to: '/network', label: 'Network' },
  { to: '/compliance', label: 'Compliance' },
]

export default function App() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">◧</span>
          <div>
            <div className="brand-name">MedGraph</div>
            <div className="brand-sub">HCP / KOL Engagement &amp; Compliance</div>
          </div>
        </div>
        <nav>
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="foot-title">Public data only</div>
          <ul>
            <li>CMS Open Payments</li>
            <li>ClinicalTrials.gov</li>
            <li>Europe PMC</li>
            <li>NPPES NPI Registry</li>
          </ul>
          <p className="disclaimer">
            Built for portfolio / interview demonstration. Not affiliated with, endorsed by, or
            containing data from any company. All figures derive from public government and
            open-science sources.
          </p>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/network" element={<NetworkPage />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/physician/:npi" element={<PhysicianPage />} />
        </Routes>
      </main>
    </div>
  )
}
