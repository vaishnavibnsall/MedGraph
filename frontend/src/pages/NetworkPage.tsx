import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { api } from '../api/client'
import { useFetch, Loading, ErrorBox } from '../hooks'
import type { NetworkGraph } from '../types'

// node colour by dominant signal tier (influence)
function colorForInfluence(v: number): string {
  if (v >= 60) return '#ffce54'
  if (v >= 35) return '#4f9dff'
  if (v >= 15) return '#37d0a5'
  return '#64748b'
}

export default function NetworkPage() {
  const [topN, setTopN] = useState(120)
  const [kHop, setKHop] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const navigate = useNavigate()
  const fgRef = useRef<any>(null)

  const graph = useFetch<NetworkGraph>(
    () => api.networkGraph({ top_n: topN, k_hop: kHop }),
    [topN, kHop],
  )
  const netStats = useFetch<any>(() => api.networkStats(), [])

  const data = graph.data

  // react-force-graph mutates nodes; keep a stable copy keyed on fetch
  const fgData = useMemo(() => {
    if (!data) return { nodes: [], links: [] }
    return {
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.links.map((l) => ({ ...l })),
    }
  }, [data])

  useEffect(() => {
    if (fgRef.current && fgData.nodes.length) {
      // @ts-ignore exist for zoomToFit
      setTimeout(() => fgRef.current?.zoomToFit(400, 60), 60)
    }
  }, [fgData])

  const handleNodeClick = useCallback((node: any) => {
    setSelected(node.id)
  }, [])

  const nodeCanvasObject = useCallback((node: any, ctx: any, scale: number) => {
    const r = Math.max(3, Math.min(14, 3 + (node.degree ?? 1) * 0.8))
    const color = colorForInfluence(node.influence ?? 0)
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
    ctx.lineWidth = 1
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'
    ctx.stroke()
    // label for larger/central nodes
    if ((scale > 1.4 && r > 5) || node.id === selected) {
      const label = node.label ?? node.id
      ctx.font = `${11 / scale}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = 'rgba(230,237,247,0.9)'
      ctx.fillText(label, node.x, node.y + r + 1)
    }
  }, [selected])

  return (
    <div>
      <div className="page-head">
        <h1>Co-investigator Network</h1>
        <p>
          A physician↔physician graph built from CMS Open Payments <strong>research</strong>{' '}
          records: every study names up to five principal investigators, and any two PIs on the
          same study are linked. Node size = degree, colour = influence tier, edge thickness =
          shared studies.
        </p>
      </div>

      <div className="controls">
        <div className="field">
          <label>Graph size</label>
          <select value={topN} onChange={(e) => setTopN(Number(e.target.value))}>
            {[60, 120, 250, 400].map((n) => (
              <option key={n} value={n}>{n} nodes</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Neighbourhood</label>
          <select value={kHop} onChange={(e) => setKHop(Number(e.target.value))}>
            {[1, 2, 3].map((n) => (
              <option key={n} value={n}>{n}-hop</option>
            ))}
          </select>
        </div>
        {selected && (
          <button className="btn ghost" onClick={() => navigate(`/physician/${selected}`)}>
            Open selected profile →
          </button>
        )}
      </div>

      {netStats.data && (
        <div className="grid cols-4" style={{ marginBottom: 16 }}>
          <div className="card"><h3>Nodes</h3><div className="stat">{netStats.data.nodes}</div></div>
          <div className="card"><h3>Edges</h3><div className="stat">{netStats.data.edges}</div></div>
          <div className="card"><h3>Density</h3><div className="stat green">{netStats.data.density}</div></div>
          <div className="card"><h3>Components</h3><div className="stat gold">{netStats.data.components}</div></div>
        </div>
      )}

      <div className="card">
        {graph.loading && <Loading />}
        {graph.error && <ErrorBox msg={graph.error} />}
        {data && (
          <div className="net-wrap">
            <ForceGraph2D
              ref={fgRef}
              graphData={fgData}
              nodeId="id"
              nodeLabel="label"
              nodeRelSize={2}
              linkWidth={(l: any) => 0.4 + Math.min(4, (l.weight ?? 1) * 0.6)}
              linkColor={() => 'rgba(148,166,192,0.35)'}
              linkDirectionalParticles={1}
              linkDirectionalParticleWidth={(l: any) => (l.weight > 2 ? 1.5 : 0)}
              nodeCanvasObject={nodeCanvasObject}
              nodeCanvasObjectMode="replace"
              onNodeClick={handleNodeClick}
              onBackgroundClick={() => setSelected(null)}
              backgroundColor="#0e1420"
              warmupTicks={60}
              cooldownTime={2600}
            />
          </div>
        )}
        <div className="net-legend">
          <span><span className="dot" style={{ background: '#ffce54' }} />High influence (≥60)</span>
          <span><span className="dot" style={{ background: '#4f9dff' }} />Mid (35–60)</span>
          <span><span className="dot" style={{ background: '#37d0a5' }} />Rising (15–35)</span>
          <span><span className="dot" style={{ background: '#64748b' }} />Low (&lt;15)</span>
          <span className="muted">Click a node to select, then open its profile.</span>
        </div>
      </div>
    </div>
  )
}
