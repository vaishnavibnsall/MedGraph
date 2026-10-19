import { Link } from 'react-router-dom'
import { api, fmtNum, fmtUSD } from '../api/client'
import { useFetch, Loading, ErrorBox } from '../hooks'
import type { Stats, TrialSummary } from '../types'

export default function Dashboard() {
  const stats = useFetch<Stats>(() => api.stats(), [])
  const trials = useFetch<TrialSummary>(() => api.trialSummary(), [])

  if (stats.loading) return <Loading />
  if (stats.error) return <ErrorBox msg={stats.error} />
  const s = stats.data!

  return (
    <div>
      <div className="page-head">
        <h1>MedGraph Overview</h1>
        <p>
          A commercial-analytics &amp; medical-affairs intelligence platform built entirely on
          public data. It unifies CMS Open Payments (pharma→physician transfers of value),
          ClinicalTrials.gov, Europe PMC and NPPES into a single KOL influence index, a
          co-investigator network, and a compliance/analytics dashboard.
        </p>
      </div>

      <div className="grid cols-4">
        <div className="card">
          <h3>Covered physicians</h3>
          <div className="stat accent">{fmtNum(s.physicians)}</div>
        </div>
        <div className="card">
          <h3>Payments analysed</h3>
          <div className="stat">{fmtNum(s.payments)}</div>
        </div>
        <div className="card">
          <h3>Industry spend (sample)</h3>
          <div className="stat gold">{fmtUSD(s.total_spend)}</div>
        </div>
        <div className="card">
          <h3>Reporting companies</h3>
          <div className="stat green">{fmtNum(s.companies)}</div>
        </div>
      </div>

      <div className="grid cols-3 section-gap">
        <div className="card">
          <h3>Co-investigator network</h3>
          <div className="stat">{fmtNum(s.edges)}<small>physician↔physician links via shared research</small></div>
          <p className="muted" style={{ marginTop: 12 }}>
            Edges are derived from CMS Open Payments <em>research</em> records, where up to five
            principal investigators are named per study — a genuine professional network rather
            than a co-authorship proxy.
          </p>
          <Link className="plain" to="/network">Explore the graph →</Link>
        </div>
        <div className="card">
          <h3>Trial portfolio</h3>
          <div className="stat">{fmtNum(trials.data?.n_trials ?? 0)}<small>registered studies pulled from ClinicalTrials.gov</small></div>
          <p className="muted" style={{ marginTop: 12 }}>
            {fmtNum(trials.data?.total_enrollment ?? 0)} total participants across sponsor
            portfolios, used to contextualise KOL trial influence and the trial landscape.
          </p>
        </div>
        <div className="card">
          <h3>Publications</h3>
          <div className="stat">{fmtNum(s.publications)}<small>Europe PMC author profiles enriched</small></div>
          <p className="muted" style={{ marginTop: 12 }}>
            Bibliometric output for top KOL candidates feeds one of the four signals in the
            multi-signal influence index.
          </p>
          <Link className="plain" to="/leaderboard">See the leaderboard →</Link>
        </div>
      </div>

      <div className="card section-gap">
        <h3>How the KOL influence index is built</h3>
        <div className="grid cols-4">
          <div>
            <div className="badge blue">30%</div>
            <strong style={{ display: 'block', margin: '6px 0 2px' }}>Publication</strong>
            <span className="muted">Europe PMC publication volume (log-scaled, min-max normalised).</span>
          </div>
          <div>
            <div className="badge green">30%</div>
            <strong style={{ display: 'block', margin: '6px 0 2px' }}>Trial engagement</strong>
            <span className="muted">Distinct research studies as principal investigator + scope proxy.</span>
          </div>
          <div>
            <div className="badge gold">25%</div>
            <strong style={{ display: 'block', margin: '6px 0 2px' }}>Network centrality</strong>
            <span className="muted">Degree + weighted degree in the co-investigator graph.</span>
          </div>
          <div>
            <div className="badge blue">15%</div>
            <strong style={{ display: 'block', margin: '6px 0 2px' }}>Payment tier</strong>
            <span className="muted">Industry engagement (general payments received, log-scaled).</span>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 14 }}>
          Each signal is transformed (log1p) to tame right-skew, min-max scaled to [0,1], then
          combined with the weights above into a transparent 0–100 composite. Every score is
          drillable so the math is auditable — no black box.
        </p>
      </div>
    </div>
  )
}
