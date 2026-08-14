'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import { fetchDCs, fetchKPIs, healthClass, fmtCurrency, fmtNum } from '@/lib/api'

export default function DashboardPage() {
  const router = useRouter()
  const [dcs, setDcs] = useState<any[]>([])
  const [kpis, setKpis] = useState<any>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([fetchDCs(), fetchKPIs()]).then(([dcData, kpiData]) => {
      setDcs(dcData.dcs || [])
      setKpis(kpiData)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const healthColor = (flag: string) => {
    if (flag === 'red') return 'red'
    if (flag === 'yellow') return 'yellow'
    return 'green'
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span>MedCare Pharma</span>
            <span className="crumb-sep">/</span>
            <span className="crumb-current">Network Dashboard</span>
          </div>
          <div className="topbar-actions">
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Analysis: 2026-08-13</span>
          </div>
        </div>

        <div className="page-body">
          <div className="page-header">
            <div className="page-title-group">
              <h1>Network Overview</h1>
              <p>
                Demand sensing &amp; replenishment status across{' '}
                {loading ? '…' : dcs.length} distribution centers,{' '}
                {loading ? '…' : (kpis.total_skus ?? 40)} SKUs
              </p>
            </div>
            <button className="btn btn-primary" id="btn-replenishment" onClick={() => router.push('/replenishment')}>
              View Replenishment Table →
            </button>
          </div>

          {/* KPI Cards */}
          <div className="kpi-grid" style={{ marginBottom: 24 }}>
            <div className="kpi-card">
              <div className="kpi-label">Critical Stockouts</div>
              <div className="kpi-value" style={{ color: kpis.critical_stockouts > 0 ? 'var(--red)' : 'var(--green)' }}>
                {loading ? '…' : kpis.critical_stockouts ?? 0}
              </div>
              <div className="kpi-sub">High-criticality SKUs at risk</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Stockout Risk Flags</div>
              <div className="kpi-value" style={{ color: 'var(--yellow)' }}>
                {loading ? '…' : kpis.total_stockout_risk ?? 0}
              </div>
              <div className="kpi-sub">DC × SKU pairs below safety stock</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Near-Expiry Value</div>
              <div className="kpi-value" style={{ color: 'var(--orange)' }}>
                {loading ? '…' : fmtCurrency(kpis.near_expiry_inventory_value ?? 0)}
              </div>
              <div className="kpi-sub">Inventory expiring within 90 days</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Est. Replenishment Cost</div>
              <div className="kpi-value">
                {loading ? '…' : fmtCurrency(kpis.estimated_total_replenishment_cost ?? 0)}
              </div>
              <div className="kpi-sub">Optimal action across network</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Model Comparison</div>
              <div className="kpi-value" style={{ fontSize: '1.05rem', paddingTop: 4 }}>
                {loading ? '…' : (kpis.global_model_metrics?.winner || 'XGBoost').replace('_', ' ').toUpperCase()}
              </div>
              <div className="kpi-sub">
                Global winner · MAE {kpis.global_model_metrics?.random_forest?.mae?.toFixed(1) ?? '—'} units/day
                <span style={{ display: 'block', marginTop: 2, fontSize: 10, color: 'var(--text-muted)' }}>
                  Per-SKU forecasting uses XGBoost vs baseline
                </span>
              </div>
            </div>
          </div>


          {/* DC Cards */}
          <h2 style={{ marginBottom: 4 }}>Distribution Centers</h2>
          <p style={{ marginBottom: 0 }}>Click a DC card to drill into SKU-level analysis</p>

          {loading ? (
            <div className="loading-wrap"><div className="spinner" /> Loading DC data…</div>
          ) : (
            <div className="dc-grid">
              {dcs.map((dc: any) => {
                const hc = healthColor(dc.dc_health)
                const healthPct = Math.round((dc.avg_health / 2) * 100)
                return (
                  <div key={dc.dc_id} className={`dc-card ${hc}`}
                    id={`dc-card-${dc.dc_id}`}
                    onClick={() => router.push(`/dc/${dc.dc_id}`)}>
                    <div className="dc-card-header">
                      <div>
                        <div className="dc-card-name" style={{ display:'flex', alignItems:'center', gap:6 }}>
                          {dc.dc_name || dc.dc_id}
                          {dc.dc_tier && (
                            <span style={{
                              fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
                              padding: '2px 6px', borderRadius: 4,
                              background: dc.dc_tier === 'Metro' ? 'var(--accent-dim)' : 'var(--yellow-dim)',
                              color: dc.dc_tier === 'Metro' ? 'var(--accent)' : 'var(--yellow)',
                              textTransform: 'uppercase',
                            }}>{dc.dc_tier}</span>
                          )}
                        </div>
                        <div className="dc-card-city">{dc.city} · {dc.region}</div>
                      </div>
                      <span className={`badge badge-${hc}`}>
                        <span className={`dot dot-${hc}`} />
                        {dc.dc_health?.toUpperCase()}
                      </span>
                    </div>

                    <div className="dc-card-stats">
                      <div className="dc-stat">
                        <div className="dc-stat-label">SKUs</div>
                        <div className="dc-stat-value">{dc.n_skus ?? 15}</div>
                      </div>
                      <div className="dc-stat">
                        <div className="dc-stat-label">At Risk</div>
                        <div className="dc-stat-value" style={{ color: dc.n_stockout_risk > 0 ? 'var(--red)' : 'var(--green)' }}>
                          {dc.n_stockout_risk ?? 0}
                        </div>
                      </div>
                      <div className="dc-stat">
                        <div className="dc-stat-label">Need Reorder</div>
                        <div className="dc-stat-value" style={{ color: dc.n_reorder_needed > 0 ? 'var(--yellow)' : 'inherit' }}>
                          {dc.n_reorder_needed ?? 0}
                        </div>
                      </div>
                      <div className="dc-stat">
                        <div className="dc-stat-label">Near Expiry</div>
                        <div className="dc-stat-value" style={{ color: dc.near_expiry_units > 0 ? 'var(--orange)' : 'inherit' }}>
                          {fmtNum(dc.near_expiry_units ?? 0)}
                        </div>
                      </div>
                    </div>

                    <div className="health-bar-wrap">
                      <div className="health-bar">
                        <div className="health-bar-fill"
                          style={{ width: `${healthPct}%`, background: `var(--${hc})` }} />
                      </div>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{healthPct}%</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
