// Thin typed fetch wrapper for the MedGraph FastAPI backend.
import type {
  Bipartite, BenchmarkRow, CompanyTotal, Concentration, GeoPoint, Health,
  InfluenceBreakdown, KolLeaderboard, MetroPoint, NaturePoint, NetworkGraph,
  OutlierSummary, ParetoPoint, PhysicianProfile, Stats, TopOutlierRow,
  TrialSummary,
} from '../types'

const BASE = ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${path}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => get<Health>('/api/health'),
  stats: () => get<Stats>('/api/stats'),

  leaderboard: (params: Record<string, string | number | undefined>) =>
    get<KolLeaderboard>(`/api/kol/leaderboard?${qs(params)}`),
  specialties: () => get<string[]>('/api/kol/specialties'),
  states: () => get<string[]>('/api/kol/states'),
  companies: (q?: string) => get<string[]>(`/api/kol/companies${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  breakdown: (npi: string) => get<InfluenceBreakdown>(`/api/kol/breakdown/${npi}`),

  networkGraph: (params: Record<string, string | number | undefined>) =>
    get<NetworkGraph>(`/api/network/graph?${qs(params)}`),
  ego: (npi: string) => get<any>(`/api/network/ego/${npi}`),
  networkStats: () => get<any>('/api/network/stats'),

  outlierSummary: () => get<OutlierSummary>('/api/compliance/outliers'),
  topOutliers: (limit = 30, company?: string) =>
    get<{ count: number; rows: TopOutlierRow[] }>(
      `/api/compliance/outliers/top?limit=${limit}${company ? `&company=${encodeURIComponent(company)}` : ''}`),
  benchmark: (anchor = 'MERCK') => get<BenchmarkRow[]>(`/api/compliance/benchmark?anchor=${encodeURIComponent(anchor)}`),
  companyTotals: () => get<CompanyTotal[]>('/api/compliance/companies'),
  pareto: () => get<ParetoPoint[]>('/api/compliance/pareto'),
  concentration: () => get<Concentration>('/api/compliance/concentration'),
  geospatial: () => get<GeoPoint[]>('/api/compliance/geospatial'),
  metro: () => get<MetroPoint[]>('/api/compliance/metro'),
  nature: () => get<NaturePoint[]>('/api/compliance/nature'),
  bipartite: () => get<Bipartite>('/api/compliance/bipartite'),

  physician: (npi: string) => get<PhysicianProfile>(`/api/physician/${npi}`),
  searchPhysician: (q: string) =>
    get<{ npi: string; name: string; specialty: string; state: string }[]>(
      `/api/physician/search/one?q=${encodeURIComponent(q)}`),

  trialSummary: () => get<TrialSummary>('/api/trials/summary'),
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') sp.set(k, String(v))
  }
  return sp.toString()
}

export const fmtUSD = (v: number, compact = true): string => {
  if (!compact) return v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`
  if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

export const fmtNum = (v: number): string => v.toLocaleString('en-US')
