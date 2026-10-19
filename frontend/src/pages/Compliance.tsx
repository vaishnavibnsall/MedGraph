import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
  Area, AreaChart,
} from 'recharts'
import { api, fmtNum, fmtUSD } from '../api/client'
import { useFetch, Loading, ErrorBox } from '../hooks'
import type {
  BenchmarkRow, Concentration, GeoPoint, MetroPoint, NaturePoint,
  OutlierSummary, ParetoPoint, TopOutlierRow, CompanyTotal,
} from '../types'

const AXIS = { stroke: '#94a6c0', fontSize: 11 }
const GRID = '#2a3852'

export default function Compliance() {
  const [anchor, setAnchor] = useState('MERCK')
  const summary = useFetch<OutlierSummary>(() => api.outlierSummary(), [])
  const topOut = useFetch<{ count: number; rows: TopOutlierRow[] }>(() => api.topOutliers(25), [])
  const bench = useFetch<BenchmarkRow[]>(() => api.benchmark(anchor), [anchor])
  const companies = useFetch<CompanyTotal[]>(() => api.companyTotals(), [])
  const pareto = useFetch<ParetoPoint[]>(() => api.pareto(), [])
  const conc = useFetch<Concentration>(() => api.concentration(), [])
  const geo = useFetch<GeoPoint[]>(() => api.geospatial(), [])
  const metro = useFetch<MetroPoint[]>(() => api.metro(), [])
  const nature = useFetch<NaturePoint[]>(() => api.nature(), [])

  return (
    <div>
      <div className="page-head">
        <h1>Compliance &amp; Spend Analytics</h1>
        <p>
          Transparency-data checks a commercial / medical-affairs team would run: payment
          outlier flagging (robust z-score vs specialty×nature cohort), Merck-vs-peer benchmarking
          by specialty, spend concentration (Pareto / Gini), geospatial distribution, and the
          nature-of-payment mix.
        </p>
      </div>

      {/* KPI strip */}
      <div className="grid cols-4">
        <div className="card">
          <h3>Payments screened</h3>
          <div className="stat">{summary.data ? fmtNum(summary.data.n_payments) : '—'}</div>
        </div>
        <div className="card">
          <h3>Outlier flags</h3>
          <div className="stat" style={{ color: 'var(--warn)' }}>
            {summary.data ? fmtNum(summary.data.n_outliers) : '—'}
          </div>
        </div>
        <div className="card">
          <h3>Outlier rate</h3>
          <div className="stat gold">
            {summary.data ? `${(summary.data.outlier_rate * 100).toFixed(2)}%` : '—'}
          </div>
        </div>
        <div className="card">
          <h3>Outlier value</h3>
          <div className="stat green">
            {summary.data ? fmtUSD(summary.data.outlier_amount) : '—'}
          </div>
        </div>
      </div>

      {/* Concentration */}
      {conc.data && (
        <div className="grid cols-3 section-gap">
          <div className="card">
            <h3>Top 1% share</h3>
            <div className="stat gold">{(conc.data.top_1pct_share * 100).toFixed(1)}%</div>
          </div>
          <div className="card">
            <h3>Top 10% share</h3>
            <div className="stat accent">{(conc.data.top_10pct_share * 100).toFixed(1)}%</div>
          </div>
          <div className="card">
            <h3>Gini coefficient</h3>
            <div className="stat">{conc.data.gini.toFixed(3)}</div>
          </div>
        </div>
      )}

      {/* Pareto + nature mix */}
      <div className="grid cols-2 section-gap">
        <div className="card">
          <h3>Spend concentration (Pareto)</h3>
          {pareto.loading && <Loading />}
          {pareto.data && (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={pareto.data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="physician_pct" tick={AXIS} label={{ value: '% of physicians (rich→poor)', position: 'insideBottom', offset: -2, fill: AXIS.stroke, fontSize: 11 }} />
                <YAxis tick={AXIS} unit="%" />
                <Tooltip contentStyle={{ background: '#1a2436', border: '1px solid #2a3852', borderRadius: 8 }} formatter={(v: any) => [`${v}%`, 'spend']} />
                <Area type="monotone" dataKey="spend_pct" stroke="#4f9dff" fill="#4f9dff33" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="card">
          <h3>Nature-of-payment mix</h3>
          {nature.loading && <Loading />}
          {nature.data && (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={nature.data.slice(0, 7)} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis type="number" tick={AXIS} tickFormatter={(v) => fmtUSD(v as number)} />
                <YAxis type="category" dataKey="nature" tick={AXIS} width={150} tickFormatter={(v) => String(v).slice(0, 24)} />
                <Tooltip contentStyle={{ background: '#1a2436', border: '1px solid #2a3852', borderRadius: 8 }} formatter={(v: any) => [fmtUSD(v), 'total']} />
                <Bar dataKey="total" fill="#37d0a5" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Benchmark */}
      <div className="card section-gap">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <h3 style={{ margin: 0 }}>Per-physician spend by specialty — anchor vs market</h3>
          <div className="field">
            <label>Anchor company</label>
            <select value={anchor} onChange={(e) => setAnchor(e.target.value)}>
              {['MERCK', 'PFIZER', 'ASTRAZENECA', 'NOVARTIS', 'ABBVIE', 'AMGEN', 'LILLY'].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>
        {bench.loading && <Loading />}
        {bench.error && <ErrorBox msg={bench.error} />}
        {bench.data && (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={bench.data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis dataKey="specialty" tick={AXIS} tickFormatter={(v) => String(v).split('|').pop()?.slice(0, 16) ?? ''} interval={0} angle={-18} textAnchor="end" height={70} />
              <YAxis tick={AXIS} tickFormatter={(v) => fmtUSD(v as number)} />
              <Tooltip contentStyle={{ background: '#1a2436', border: '1px solid #2a3852', borderRadius: 8 }} formatter={(v: any, n: any) => [fmtUSD(v), n === 'anchor_mean' ? `${anchor} mean` : 'market mean']} />
              <Bar dataKey="anchor_mean" fill="#4f9dff" radius={[4, 4, 0, 0]} />
              <Bar dataKey="market_mean" fill="#64748b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
        <p className="muted" style={{ marginTop: 8 }}>
          Mean per-physician general payments received by {anchor} (blue) vs the whole market
          (grey) within each specialty — the core lens for SFE targeting and share-of-wallet.
        </p>
      </div>

      {/* Company totals + geospatial */}
      <div className="grid cols-2 section-gap">
        <div className="card">
          <h3>Company spend benchmarking</h3>
          {companies.loading && <Loading />}
          {companies.data && (
            <div className="table-scroll" style={{ maxHeight: 340 }}>
              <table>
                <thead>
                  <tr><th>Company</th><th className="num">Total</th><th className="num">Median</th><th className="num">Physicians</th></tr>
                </thead>
                <tbody>
                  {companies.data.map((c) => (
                    <tr key={c.company_name}>
                      <td>{c.company_name}</td>
                      <td className="num">{fmtUSD(c.total)}</td>
                      <td className="num">{fmtUSD(c.median)}</td>
                      <td className="num">{fmtNum(c.n_physicians)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="card">
          <h3>Geospatial spend — top metros</h3>
          {metro.loading && <Loading />}
          {metro.data && (
            <ResponsiveContainer width="100%" height={340}>
              <BarChart data={metro.data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis type="number" tick={AXIS} tickFormatter={(v) => fmtUSD(v as number)} />
                <YAxis type="category" dataKey="metro" tick={AXIS} width={90} />
                <Tooltip contentStyle={{ background: '#1a2436', border: '1px solid #2a3852', borderRadius: 8 }} formatter={(v: any) => [fmtUSD(v), 'total']} />
                <Bar dataKey="total" fill="#b388ff" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* State map-ish + outlier table */}
      <div className="grid cols-2 section-gap">
        <div className="card">
          <h3>Spend by state</h3>
          {geo.loading && <Loading />}
          {geo.data && (
            <ResponsiveContainer width="100%" height={340}>
              <BarChart data={geo.data.slice(0, 15)} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="state" tick={AXIS} />
                <YAxis tick={AXIS} tickFormatter={(v) => fmtUSD(v as number)} />
                <Tooltip contentStyle={{ background: '#1a2436', border: '1px solid #2a3852', borderRadius: 8 }} formatter={(v: any, n: any) => [n === 'total' ? fmtUSD(v) : fmtNum(v as number), n === 'total' ? 'total' : 'payments']} />
                <Bar dataKey="total" fill="#4f9dff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="card">
          <h3>Top payment outliers (robust z ≥ 4)</h3>
          {topOut.loading && <Loading />}
          {topOut.data && (
            <div className="table-scroll" style={{ maxHeight: 340 }}>
              <table>
                <thead>
                  <tr><th>Physician</th><th>Company</th><th className="num">Amount</th><th className="num">z</th></tr>
                </thead>
                <tbody>
                  {topOut.data.rows.map((r, i) => (
                    <tr key={i}>
                      <td>
                        {r.name}
                        <div className="muted" style={{ fontSize: 11 }}>{r.specialty?.split('|').pop()}</div>
                      </td>
                      <td>{r.company_name?.slice(0, 22)}</td>
                      <td className="num">{fmtUSD(r.amount, false)}</td>
                      <td className="num"><span className="badge red">{r.robust_z.toFixed(1)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
