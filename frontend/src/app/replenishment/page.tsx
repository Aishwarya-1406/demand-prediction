'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import { fetchReplenishment, fetchKPIs, critClass, trendClass, trendIcon, fmtCurrency, fmtNum } from '@/lib/api'

const HEALTH_COLOR: Record<string, string> = { red: 'var(--red)', yellow: 'var(--yellow)', green: 'var(--green)' }

export default function ReplenishmentPage() {
  const router = useRouter()
  const [rows, setRows] = useState<any[]>([])
  const [kpis, setKpis] = useState<any>({})
  const [loading, setLoading] = useState(true)
  const [dcFilter, setDcFilter] = useState('')
  const [critFilter, setCritFilter] = useState('')
  const [riskFilter, setRiskFilter] = useState('')
  const [sortCol, setSortCol] = useState('days_of_stock')

  const load = useCallback(() => {
    setLoading(true)
    const params: Record<string, string> = {}
    if (dcFilter) params.dc_id = dcFilter
    if (critFilter) params.criticality = critFilter
    if (riskFilter) params.risk = riskFilter
    params.sort_by = sortCol
    Promise.all([fetchReplenishment(params), fetchKPIs()]).then(([rData, kData]) => {
      setRows(rData.rows || [])
      setKpis(kData)
      setLoading(false)
    })
  }, [dcFilter, critFilter, riskFilter, sortCol])

  useEffect(() => { load() }, [load])

  const actionColor = (action: string) => {
    if (action === 'local_supplier') return 'var(--red)'
    if (action === 'dc_transfer') return 'var(--accent)'
    if (action === 'regular_supplier') return 'var(--green)'
    return 'var(--text-muted)'
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span style={{ cursor: 'pointer' }} onClick={() => router.push('/dashboard')}>Dashboard</span>
            <span className="crumb-sep">/</span>
            <span className="crumb-current">Replenishment Plan</span>
          </div>
          <div className="topbar-actions">
            <select id="filter-dc" value={dcFilter} onChange={e => setDcFilter(e.target.value)}>
              <option value="">All DCs</option>
              {['DC001','DC002','DC003','DC004','DC005'].map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <select id="filter-crit" value={critFilter} onChange={e => setCritFilter(e.target.value)}>
              <option value="">All Criticality</option>
              {['High','Medium','Low'].map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select id="filter-risk" value={riskFilter} onChange={e => setRiskFilter(e.target.value)}>
              <option value="">All Status</option>
              <option value="red">At Risk</option>
              <option value="yellow">Reorder</option>
              <option value="green">OK</option>
            </select>
          </div>
        </div>

        <div className="page-body">
          <div className="page-header">
            <div className="page-title-group">
              <h1>Network Replenishment Plan</h1>
              <p>DACDF-fused recommendations across 5 DCs, 15 SKUs. Analysis date: 2026-08-13.</p>
            </div>
          </div>

          {/* KPIs */}
          <div className="kpi-grid" style={{ marginBottom: 20 }}>
            <div className="kpi-card">
              <div className="kpi-label">Critical Stockouts</div>
              <div className="kpi-value" style={{ color: 'var(--red)' }}>{kpis.critical_stockouts ?? '…'}</div>
              <div className="kpi-sub">High-criticality SKUs below safety stock</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Total At Risk</div>
              <div className="kpi-value" style={{ color: 'var(--yellow)' }}>{kpis.total_stockout_risk ?? '…'}</div>
              <div className="kpi-sub">DC × SKU pairs flagged</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Near-Expiry Value</div>
              <div className="kpi-value">{fmtCurrency(kpis.near_expiry_inventory_value ?? 0)}</div>
              <div className="kpi-sub">Inventory expiring &lt;90 days</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Total Plan Cost</div>
              <div className="kpi-value">{fmtCurrency(kpis.estimated_total_replenishment_cost ?? 0)}</div>
              <div className="kpi-sub">Optimal actions if all executed</div>
            </div>
          </div>

          {/* Action distribution */}
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            {['no_action','dc_transfer','regular_supplier','local_supplier'].map(action => {
              const count = rows.filter(r => r.best_action === action).length
              const label = action.replace('_', ' ')
              return (
                <div key={action} style={{ padding: '6px 14px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 20, fontSize: 12 }}>
                  <span style={{ color: actionColor(action), fontWeight: 600 }}>{count}</span>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>{label}</span>
                </div>
              )
            })}
          </div>

          {/* Table */}
          {loading ? (
            <div className="loading-wrap"><div className="spinner" /> Loading…</div>
          ) : (
            <div className="card" style={{ overflow: 'hidden' }}>
              <div className="card-header">
                <div className="card-title">Replenishment Actions — {rows.length} rows</div>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" id="replenishment-table">
                  <thead>
                    <tr>
                      {[
                        ['dc_id','DC'], ['sku_id','SKU'], ['criticality','Priority'],
                        ['stockout_risk','Status'], ['days_of_stock','Days Stock'],
                        ['required_qty','Req Qty'], ['trend','Trend'],
                        ['near_expiry_qty','Near Expiry'], ['best_action_label','AI Action'],
                        ['lead_time_days','Lead Time'], ['est_cost','Cost'],
                        ['ai_confidence','Confidence'],
                      ].map(([col, label]) => (
                        <th key={col} onClick={() => setSortCol(col)}>{label} {sortCol === col ? '↑' : ''}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row: any, i: number) => (
                      <tr key={i} id={`rep-row-${row.dc_id}-${row.sku_id}`}
                        onClick={() => router.push(`/dc/${row.dc_id}/${row.sku_id}`)}>
                        <td style={{ fontSize: 11, fontWeight: 600 }}>{row.dc_id}<div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400 }}>{row.dc_name}</div></td>
                        <td>
                          <div style={{ fontWeight: 600 }}>{row.sku_id}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{row.sku_name}</div>
                        </td>
                        <td><span className={`badge ${critClass(row.criticality)}`}>{row.criticality}</span></td>
                        <td>
                          <span className={`badge badge-${row.stockout_risk}`}>
                            <span className={`dot dot-${row.stockout_risk}`} />
                            {row.stockout_risk === 'red' ? 'At Risk' : row.stockout_risk === 'yellow' ? 'Reorder' : 'OK'}
                          </span>
                        </td>
                        <td className="num" style={{ color: HEALTH_COLOR[row.stockout_risk] }}>
                          {row.days_of_stock === 999 ? '∞' : row.days_of_stock?.toFixed(1)}d
                        </td>
                        <td className="num">{fmtNum(row.required_qty)}</td>
                        <td><span className={`trend-chip ${trendClass(row.trend)}`}>{trendIcon(row.trend)} {row.trend}</span></td>
                        <td className="num" style={{ color: row.near_expiry_qty > 0 ? 'var(--orange)' : 'inherit' }}>
                          {fmtNum(row.near_expiry_qty)}
                        </td>
                        <td>
                          <span style={{ fontSize: 12, fontWeight: 600, color: actionColor(row.best_action) }}>
                            {row.best_action_label}
                          </span>
                          {row.source && row.best_action === 'dc_transfer' && (
                            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>from {row.source}</div>
                          )}
                        </td>
                        <td className="num">{row.lead_time_days}d</td>
                        <td className="num">{fmtCurrency(row.est_cost)}</td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <div style={{ width: 40, height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
                              <div style={{ height: '100%', width: `${(row.ai_confidence || 0.5) * 100}%`, background: 'var(--accent)', borderRadius: 2 }} />
                            </div>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                              {Math.round((row.ai_confidence || 0.5) * 100)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
