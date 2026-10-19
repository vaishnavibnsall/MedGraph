// Shared API types mirroring the FastAPI response models.

export interface Health {
  status: string
  db: string
  physicians: number
  payments: number
  edges: number
  trials: number
}

export interface Stats {
  physicians: number
  companies: number
  payments: number
  research_payments: number
  edges: number
  trials: number
  publications: number
  total_spend: number
  program_year: number
}

export interface KolRow {
  rank: number
  npi: string
  name: string
  specialty: string
  state: string
  influence_score: number
  publication_score: number
  trial_score: number
  network_score: number
  payment_score: number
  publications: number
  trial_count: number
  degree: number
  total_received: number
  n_companies: number
}

export interface KolLeaderboard {
  total: number
  rows: KolRow[]
}

export interface InfluenceBreakdown {
  npi: string
  name: string
  weights: Record<string, number>
  signals: Record<string, number>
}

export interface GraphNode {
  id: string
  label: string
  degree?: number
  wdegree?: number
  betweenness?: number
  influence?: number
}

export interface GraphLink {
  source: string
  target: string
  weight: number
  amount: number
}

export interface NetworkGraph {
  nodes: GraphNode[]
  links: GraphLink[]
  n_nodes: number
  n_links: number
}

export interface OutlierSummary {
  n_payments: number
  n_outliers: number
  outlier_rate: number
  outlier_amount: number
  top_companies: { company: string; count: number; amount: number }[]
}

export interface TopOutlierRow {
  npi: string
  name: string
  specialty: string
  state: string
  company_name: string
  amount: number
  nature: string
  form: string
  cohort_median: number
  robust_z: number
}

export interface BenchmarkRow {
  specialty: string
  anchor_mean: number
  anchor_median: number
  anchor_physicians: number
  market_mean: number
  market_median: number
  market_physicians: number
  peer_mean: number
  peer_median: number
  anchor_vs_market_mean: number | null
}

export interface CompanyTotal {
  company_name: string
  total: number
  mean: number
  median: number
  n: number
  n_physicians: number
}

export interface ParetoPoint {
  physician_pct: number
  spend_pct: number
}

export interface Concentration {
  top_1pct_share: number
  top_10pct_share: number
  gini: number
  n_physicians: number
  total_spend: number
}

export interface GeoPoint {
  state: string
  total: number
  mean: number
  n_payments: number
  n_physicians: number
}

export interface MetroPoint {
  metro: string
  total: number
  mean: number
  n_payments: number
  n_physicians: number
}

export interface NaturePoint {
  nature: string
  total: number
  mean: number
  n: number
}

export interface Bipartite {
  physicians: string[]
  companies: string[]
  matrix: number[][]
}

export interface PhysicianNeighbor {
  npi: string
  name: string
  shared_studies: number
  shared_amount: number
}

export interface PhysicianProfile {
  npi: string
  name: string
  specialty: string
  primary_type: string
  city: string
  state: string
  influence: KolRow | null
  payments_by_company: { company_name: string; total: number; n: number }[]
  payments_by_nature: { nature: string; total: number; n: number }[]
  research: { company_name: string; amount: number; date: string; study_id: string; form: string }[]
  publications: {
    query_name: string
    hit_count: number
    first_year: number | null
    last_year: number | null
    top_journals: string
  } | null
  nppes: {
    credential: string
    primary_specialty: string
    taxonomy: string
    state: string
    city: string
  } | null
  network_neighbors: PhysicianNeighbor[]
  trials: { nct_id: string; title: string; sponsor: string; status: string; enrollment: number }[]
}

export interface TrialSummary {
  n_trials: number
  total_enrollment: number
  by_sponsor: { sponsor: string; count: number; enrollment: number }[]
  by_phase: { phase: string; count: number }[]
}
