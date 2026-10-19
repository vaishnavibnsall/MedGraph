import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, fmtNum, fmtUSD } from '../api/client'
import { useFetch, Loading, ErrorBox } from '../hooks'
import type { KolLeaderboard, KolRow } from '../types'

function SignalBars({ row }: { row: KolRow }) {
  const sigs = [
    { cls: 'pub', v: row.publication_score, label: 'publication' },
    { cls: 'trial', v: row.trial_score, label: 'trial' },
    { cls: 'net', v: row.network_score, label: 'network' },
    { cls: 'pay', v: row.payment_score, label: 'payment' },
  ]
  return (
    <div className="sigs" title={sigs.map((s) => `${s.label}: ${s.v.toFixed(0)}`).join(' · ')}>
      {sigs.map((s) => (
        <div key={s.cls} className={`sig ${s.cls}`} style={{ height: Math.max(4, (s.v / 100) * 20) }} />
      ))}
    </div>
  )
}

export default function Leaderboard() {
  const [specialty, setSpecialty] = useState('')
  const [state, setState] = useState('')
  const [company, setCompany] = useState('')
  const [limit, setLimit] = useState(50)
  const navigate = useNavigate()

  const specialties = useFetch<string[]>(() => api.specialties(), [])
  const states = useFetch<string[]>(() => api.states(), [])
  const companies = useFetch<string[]>(() => api.companies(), [])
  const board = useFetch<KolLeaderboard>(
    () => api.leaderboard({ specialty, state, company, limit }),
    [specialty, state, company, limit],
  )

  const rows = useMemo(() => board.data?.rows ?? [], [board.data])

  return (
    <div>
      <div className="page-head">
        <h1>KOL Leaderboard</h1>
        <p>
          Ranked by the multi-signal influence index. Filter by specialty, state, or a specific
          reporting company to segment the field. Click any row for the full physician profile.
        </p>
      </div>

      <div className="controls">
        <div className="field">
          <label>Specialty</label>
          <select value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
            <option value="">All specialties</option>
            {(specialties.data ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>State</label>
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">All states</option>
            {(states.data ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Engaged company</label>
          <select value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">All companies</option>
            {(companies.data ?? []).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Rows</label>
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[25, 50, 100, 200].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <button className="btn ghost" onClick={() => { setSpecialty(''); setState(''); setCompany('') }}>
          Reset
        </button>
      </div>

      <div className="card">
        {board.loading && <Loading />}
        {board.error && <ErrorBox msg={board.error} />}
        {!board.loading && !board.error && (
          <>
            <h3>{fmtNum(board.data!.total)} physicians match</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Physician</th>
                    <th>Specialty</th>
                    <th>ST</th>
                    <th className="num">Index</th>
                    <th>Signals (pub/trial/net/pay)</th>
                    <th className="num">Pubs</th>
                    <th className="num">Trials</th>
                    <th className="num">Degree</th>
                    <th className="num">Received</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.npi} onClick={() => navigate(`/physician/${r.npi}`)}>
                      <td className="mono">{r.rank}</td>
                      <td>
                        <strong>{r.name}</strong>
                        <div className="muted mono" style={{ fontSize: 11 }}>{r.npi}</div>
                      </td>
                      <td>{r.specialty}</td>
                      <td>{r.state}</td>
                      <td className="num">
                        <span className={r.influence_score >= 60 ? 'badge gold' : 'badge blue'}>
                          {r.influence_score.toFixed(1)}
                        </span>
                      </td>
                      <td><SignalBars row={r} /></td>
                      <td className="num">{r.publications}</td>
                      <td className="num">{r.trial_count}</td>
                      <td className="num">{r.degree}</td>
                      <td className="num">{fmtUSD(r.total_received)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
