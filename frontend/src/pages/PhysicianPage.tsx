import { useNavigate, useParams } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, fmtNum, fmtUSD } from '../api/client'
import { useFetch, Loading, ErrorBox } from '../hooks'
import type { PhysicianProfile } from '../types'

const AXIS = { stroke: '#94a6c0', fontSize: 11 }
const GRID = '#2a3852'

function SignalRing({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div style={{ textAlign: 'center' }}>
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="30" fill="none" stroke="#202c42" strokeWidth="8" />
        <circle
          cx="36" cy="36" r="30" fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={`${(pct / 100) * 188.5} 188.5`} strokeLinecap="round"
          transform="rotate(-90 36 36)"
        />
        <text x="36" y="40" textAnchor="middle" fill="#e6edf7" fontSize="15" fontWeight="700">
          {value.toFixed(0)}
        </text>
      </svg>
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
    </div>
  )
}

export default function PhysicianPage() {
  const { npi } = useParams<{ npi: string }>()
  const navigate = useNavigate()
  const p = useFetch<PhysicianProfile>(() => api.physician(npi!), [npi])

  if (p.loading) return <Loading />
  if (p.error) return <ErrorBox msg={p.error} />
  const d = p.data!
  const infl = d.influence

  return (
    <div>
      <button className="btn ghost" onClick={() => navigate(-1)} style={{ marginBottom: 14 }}>
        ← Back
      </button>

      <div className="card profile-head">
        <div>
          <h1 style={{ margin: '0 0 4px', fontSize: 24 }}>{d.name}</h1>
          <div className="muted">{d.specialty || 'Specialty n/a'} · {d.city}, {d.state}</div>
          <div className="mono muted" style={{ fontSize: 12, marginTop: 4 }}>NPI {d.npi}</div>
          {infl && (
            <div className="chip-row">
              <span className="chip">Rank <strong>#{infl.rank}</strong></span>
              <span className="chip">Received <strong>{fmtUSD(infl.total_received)}</strong></span>
              <span className="chip">Companies <strong>{infl.n_companies}</strong></span>
              <span className="chip">Network degree <strong>{infl.degree}</strong></span>
              <span className="chip">Publications <strong>{infl.publications}</strong></span>
            </div>
          )}
        </div>
        {infl && (
          <div className="ring-wrap">
            <div style={{ textAlign: 'center' }}>
              <svg width="120" height="120" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" fill="none" stroke="#202c42" strokeWidth="12" />
                <circle
                  cx="60" cy="60" r="50" fill="none" stroke="#ffce54" strokeWidth="12"
                  strokeDasharray={`${(infl.influence_score / 100) * 314} 314`} strokeLinecap="round"
                  transform="rotate(-90 60 60)"
                />
                <text x="60" y="66" textAnchor="middle" fill="#e6edf7" fontSize="26" fontWeight="700">
                  {infl.influence_score.toFixed(0)}
                </text>
              </svg>
              <div className="muted" style={{ fontSize: 11 }}>Influence index</div>
            </div>
            <SignalRing label="Publication" value={infl.publication_score} color="#b388ff" />
            <SignalRing label="Trial" value={infl.trial_score} color="#37d0a5" />
            <SignalRing label="Network" value={infl.network_score} color="#ffce54" />
            <SignalRing label="Payment" value={infl.payment_score} color="#4f9dff" />
          </div>
        )}
      </div>

      <div className="grid cols-2 section-gap">
        <div className="card">
          <h3>Payments by company</h3>
          {d.payments_by_company.length === 0 && <div className="muted">No general payments in sample.</div>}
          {d.payments_by_company.length > 0 && (
            <ResponsiveContainer width="100%" height={Math.max(180, d.payments_by_company.length * 34)}>
              <BarChart data={d.payments_by_company} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis type="number" tick={AXIS} tickFormatter={(v) => fmtUSD(v as number)} />
                <YAxis type="category" dataKey="company_name" tick={AXIS} width={130} tickFormatter={(v) => String(v).slice(0, 18)} />
                <Tooltip contentStyle={{ background: '#1a2436', border: '1px solid #2a3852', borderRadius: 8 }} formatter={(v: any) => [fmtUSD(v), 'total']} />
                <Bar dataKey="total" fill="#4f9dff" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="card">
          <h3>Payments by nature</h3>
          {d.payments_by_nature.length === 0 && <div className="muted">No data.</div>}
          {d.payments_by_nature.length > 0 && (
            <ResponsiveContainer width="100%" height={Math.max(180, d.payments_by_nature.length * 30)}>
              <BarChart data={d.payments_by_nature} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis type="number" tick={AXIS} tickFormatter={(v) => fmtUSD(v as number)} />
                <YAxis type="category" dataKey="nature" tick={AXIS} width={150} tickFormatter={(v) => String(v).slice(0, 22)} />
                <Tooltip contentStyle={{ background: '#1a2436', border: '1px solid #2a3852', borderRadius: 8 }} formatter={(v: any) => [fmtUSD(v), 'total']} />
                <Bar dataKey="total" fill="#37d0a5" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="grid cols-3 section-gap">
        <div className="card">
          <h3>Research engagements</h3>
          {d.research.length === 0 && <div className="muted">No research payments in sample.</div>}
          <div className="table-scroll" style={{ maxHeight: 260 }}>
            <table>
              <thead><tr><th>Company</th><th>Study</th><th className="num">Amount</th></tr></thead>
              <tbody>
                {d.research.map((r, i) => (
                  <tr key={i}>
                    <td>{r.company_name?.slice(0, 18)}</td>
                    <td className="mono" style={{ fontSize: 11 }}>{r.study_id || r.date}</td>
                    <td className="num">{fmtUSD(r.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <h3>Co-investigator network</h3>
          {d.network_neighbors.length === 0 && <div className="muted">No co-investigator links in sample.</div>}
          <div className="table-scroll" style={{ maxHeight: 260 }}>
            <table>
              <thead><tr><th>Colleague</th><th className="num">Shared studies</th></tr></thead>
              <tbody>
                {d.network_neighbors.slice(0, 15).map((nb) => (
                  <tr key={nb.npi} onClick={() => navigate(`/physician/${nb.npi}`)}>
                    <td>{nb.name}</td>
                    <td className="num">{nb.shared_studies}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <h3>Bibliometric &amp; registry</h3>
          {d.publications ? (
            <div className="kv">
              <span className="k">Europe PMC hits</span><span>{fmtNum(d.publications.hit_count)}</span>
              <span className="k">Years</span><span>{d.publications.first_year ?? '—'} → {d.publications.last_year ?? '—'}</span>
              <span className="k">Query</span><span className="mono" style={{ fontSize: 11 }}>{d.publications.query_name}</span>
            </div>
          ) : (
            <div className="muted">No publication match (author-name matching is best-effort).</div>
          )}
          {d.nppes && (
            <div className="kv" style={{ marginTop: 14 }}>
              <span className="k">Credential</span><span>{d.nppes.credential || '—'}</span>
              <span className="k">NPPES taxonomy</span><span>{d.nppes.taxonomy || '—'}</span>
            </div>
          )}
        </div>
      </div>

      {d.trials.length > 0 && (
        <div className="card section-gap">
          <h3>Associated trials (ClinicalTrials.gov)</h3>
          <div className="table-scroll" style={{ maxHeight: 300 }}>
            <table>
              <thead><tr><th>NCT</th><th>Title</th><th>Sponsor</th><th className="num">Enrollment</th></tr></thead>
              <tbody>
                {d.trials.map((t) => (
                  <tr key={t.nct_id}>
                    <td><a className="plain mono" href={`https://clinicaltrials.gov/study/${t.nct_id}`} target="_blank" rel="noreferrer">{t.nct_id}</a></td>
                    <td>{t.title?.slice(0, 60)}</td>
                    <td>{t.sponsor}</td>
                    <td className="num">{fmtNum(t.enrollment)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
