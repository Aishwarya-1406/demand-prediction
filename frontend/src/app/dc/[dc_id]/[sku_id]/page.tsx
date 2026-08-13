'use client'
import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import Sidebar from '@/components/Sidebar'
import { fetchSkuDetail, critClass, trendClass, trendIcon, fmtCurrency, fmtNum } from '@/lib/api'

/* ─── helpers ─────────────────────────────────────────────── */
const HC: Record<string, string> = { red: 'var(--red)', yellow: 'var(--yellow)', green: 'var(--green)' }

function Stat({ label, value, color }: { label: string; value: any; color?: string }) {
  return (
    <div className="stat-row">
      <span className="label">{label}</span>
      <span className="value" style={color ? { color } : {}}>{value}</span>
    </div>
  )
}

function SectionCard({ title, icon, children, wide }: any) {
  return (
    <div className={`card${wide ? ' panel-wide' : ''}`}>
      <div className="card-header">
        <div className="card-title"><span>{icon}</span> {title}</div>
      </div>
      <div className="card-body">{children}</div>
    </div>
  )
}

/* ─── Panel A: Demand Forecast ────────────────────────────── */
function ForecastPanel({ data }: { data: any }) {
  const fcast = data.forecast || {}
  const chartData: any[] = fcast.chart_data || []
  // Show last 30 actual + 14 future
  const display = chartData.slice(-44)

  return (
    <>
      <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        {[
          { label: 'Winner', val: (fcast.winner || 'baseline').replace('_', ' ').toUpperCase(), col: 'var(--accent)' },
          { label: 'MAE', val: fcast.mae != null ? `${fcast.mae} units/day` : '—' },
          { label: 'RMSE', val: fcast.rmse != null ? `${fcast.rmse}` : '—' },
          { label: 'Trend', val: <span className={`trend-chip ${trendClass(data.trend)}`}>{trendIcon(data.trend)} {data.trend}</span> },
        ].map(m => (
          <div key={m.label} style={{ padding: '6px 12px', background: 'var(--bg-card-2)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{m.label}</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: m.col || 'var(--text-primary)', marginTop: 2 }}>{m.val}</div>
          </div>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={display} margin={{ top: 4, right: 12, left: -10, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
            tickFormatter={d => d?.slice(5)} interval={6} />
          <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
          <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: 'var(--text-muted)' }} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line type="monotone" dataKey="actual" stroke="var(--text-secondary)"
            dot={false} strokeWidth={1.5} name="Actual" />
          <Line type="monotone" dataKey="predicted" stroke="var(--accent)"
            dot={false} strokeWidth={2} strokeDasharray="4 2" name="Forecast" />
        </LineChart>
      </ResponsiveContainer>

      {/* SHAP drivers */}
      {fcast.shap_drivers?.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Top Forecast Drivers (SHAP)
          </div>
          {fcast.shap_drivers.map((d: any, i: number) => (
            <div key={i} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, marginBottom: 3 }}>
                <span style={{ color: 'var(--text-secondary)' }}>{d.feature.replace(/_/g, ' ')}</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{d.importance.toFixed(3)}</span>
              </div>
              <div className="score-bar">
                <div className="score-bar-fill" style={{ width: `${Math.min(d.importance * 100, 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 12, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {[
          { label: 'Next 7d forecast', val: fmtNum(fcast.forecast_next_14d?.slice(0,7).reduce((a:number,b:number)=>a+b,0) || 0) + ' units' },
          { label: 'Demand during lead time (regular, 7d)', val: fmtNum(fcast.demand_during_lead_time_regular || 0) + ' units' },
          { label: 'Demand during lead time (local, 2d)', val: fmtNum(fcast.demand_during_lead_time_local || 0) + ' units' },
        ].map(s => (
          <div key={s.label} style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {s.label}: <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{s.val}</strong>
          </div>
        ))}
      </div>
    </>
  )
}

/* ─── Panel B: Inventory Status ───────────────────────────── */
function InventoryPanel({ data }: { data: any }) {
  const max = data.reorder_point * 1.8 || 1
  const usablePct = Math.min((data.usable_inventory / max) * 100, 100)
  const physPct = Math.min((data.physical_inventory / max) * 100, 100)
  const ssPct = Math.min((data.safety_stock / max) * 100, 100)
  const ropPct = Math.min((data.reorder_point / max) * 100, 100)

  return (
    <>
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>
          <span>0</span><span>Usable</span><span>Safety Stock</span><span>Reorder Pt</span>
        </div>
        <div className="inv-gauge">
          <div className="inv-gauge-fill" style={{ width: `${physPct}%`, background: 'var(--border)', position:'absolute', height:'100%', borderRadius:4 }} />
          <div className="inv-gauge-fill" style={{ width: `${usablePct}%`, background: HC[data.health_flag] || 'var(--green)', position:'absolute', height:'100%', borderRadius:4 }} />
          <div className="inv-gauge-marker" style={{ left: `${ssPct}%`, background: 'var(--red)' }}>
            <div className="inv-gauge-label">SS</div>
          </div>
          <div className="inv-gauge-marker" style={{ left: `${ropPct}%`, background: 'var(--yellow)' }}>
            <div className="inv-gauge-label">ROP</div>
          </div>
        </div>
        <div style={{ height: 28 }} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
        {[
          { label: 'Physical Inventory', val: fmtNum(data.physical_inventory), col: 'var(--text-primary)' },
          { label: 'Reserved Inventory', val: fmtNum(data.reserved_inventory), col: 'var(--text-muted)' },
          { label: 'Usable Inventory', val: fmtNum(data.usable_inventory), col: HC[data.health_flag] },
          { label: 'Inbound Today', val: fmtNum(data.inbound_inventory), col: 'var(--teal)' },
          { label: 'Safety Stock', val: fmtNum(data.safety_stock), col: 'var(--red)' },
          { label: 'Reorder Point', val: fmtNum(data.reorder_point), col: 'var(--yellow)' },
        ].map(s => (
          <div key={s.label} style={{ padding: '8px 10px', background: 'var(--bg-card-2)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</div>
            <div style={{ fontSize: 17, fontWeight: 700, fontFamily: 'var(--font-mono)', color: s.col, marginTop: 2 }}>{s.val}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <span className={`badge badge-${data.health_flag}`}>
          <span className={`dot dot-${data.health_flag}`} />
          {data.health_flag === 'red' ? 'Below Safety Stock' : data.health_flag === 'yellow' ? 'Below Reorder Point' : 'Healthy'}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          ~{data.days_of_stock === 999 ? '∞' : data.days_of_stock} days of stock
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Projected stockout: <strong style={{ color: data.days_of_stock < 14 ? 'var(--red)' : 'var(--text-primary)' }}>{data.projected_stockout_date}</strong>
        </span>
      </div>
    </>
  )
}

/* ─── Panel C: FEFO / Batches ─────────────────────────────── */
function FEFOPanel({ data }: { data: any }) {
  const batches: any[] = (data.batches || []).sort((a: any, b: any) =>
    new Date(a.expiry_date).getTime() - new Date(b.expiry_date).getTime()
  )
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Batch ID</th><th>Qty</th><th>Manufacture Date</th>
            <th>Expiry Date</th><th>Days to Expiry</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b: any, i: number) => {
            const isNear = b.days_to_expiry != null && b.days_to_expiry <= 90
            return (
              <tr key={i} className={isNear ? 'fefo-row-near' : 'fefo-row-normal'}>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{b.batch_id}</td>
                <td className="num">{fmtNum(b.quantity)}</td>
                <td style={{ fontSize: 11 }}>{b.manufacture_date}</td>
                <td style={{ fontSize: 11, color: isNear ? 'var(--yellow)' : 'inherit' }}>{b.expiry_date}</td>
                <td className="num" style={{ color: b.days_to_expiry <= 30 ? 'var(--red)' : b.days_to_expiry <= 90 ? 'var(--yellow)' : 'inherit' }}>
                  {b.days_to_expiry}d
                </td>
                <td>
                  <span className={`badge ${b.batch_status === 'near_expiry' ? 'badge-yellow' : 'badge-green'}`}>
                    {b.batch_status}
                  </span>
                </td>
              </tr>
            )
          })}
          {batches.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No batch data</td></tr>}
        </tbody>
      </table>
      {data.near_expiry_qty > 0 && (
        <div style={{ marginTop: 10, padding: '8px 12px', background: 'var(--yellow-dim)', borderRadius: 'var(--radius-sm)', fontSize: 12, color: 'var(--yellow)' }}>
          ⚠ {fmtNum(data.near_expiry_qty)} units expiring within 90 days — transfer or consume urgently
        </div>
      )}
    </div>
  )
}

/* ─── Panel D: Replenishment Requirement ──────────────────── */
function RequirementPanel({ data }: { data: any }) {
  const f = data.forecast || {}
  const dlt = f.demand_during_lead_time_regular || 0
  const ss = data.safety_stock || 0
  const usable = data.usable_inventory || 0
  const inbound = data.inbound_inventory || 0
  const req = data.replenishment_requirement || 0

  return (
    <>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 2.2, padding: '4px 0' }}>
        <div>Demand during lead time (7d) = <strong style={{ color: 'var(--text-primary)' }}>{fmtNum(dlt)}</strong></div>
        <div>+ Safety Stock = <strong style={{ color: 'var(--red)' }}>{fmtNum(ss)}</strong></div>
        <div>− Usable Inventory = <strong style={{ color: 'var(--green)' }}>{fmtNum(usable)}</strong></div>
        <div>− Pending Inbound = <strong style={{ color: 'var(--teal)' }}>{fmtNum(inbound)}</strong></div>
        <div style={{ borderTop: '1px solid var(--border)', marginTop: 4, paddingTop: 8 }}>
          = <strong style={{ fontSize: 20, color: req > 0 ? 'var(--accent)' : 'var(--green)' }}>{fmtNum(Math.max(0, req))} units</strong>
          {req <= 0 && <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--green)' }}>✓ No replenishment needed</span>}
        </div>
      </div>
    </>
  )
}

/* ─── Panel E: Option Comparison ──────────────────────────── */
function OptionsPanel({ data }: { data: any }) {
  const options: any[] = data.options || []
  const dacdf = data.dacdf || {}
  const winnerOpt = dacdf.final_option

  return (
    <div className="option-grid">
      {options.map((opt: any) => {
        const isWinner = opt.option === winnerOpt
        const infeasible = !opt.feasible
        return (
          <div key={opt.option}
            className={`option-card ${isWinner ? 'winner' : ''} ${infeasible ? 'infeasible' : ''}`}
            id={`opt-${opt.option}`}>
            <div className="option-name">{opt.label}</div>
            <div className="option-cost">{fmtCurrency(opt.total_cost)}</div>
            <div className="option-metric"><span>Qty</span><span className="val">{fmtNum(opt.qty)}</span></div>
            <div className="option-metric"><span>Lead Time</span><span className="val">{opt.lead_time_days}d</span></div>
            <div className="option-metric"><span>Unit Cost</span><span className="val">{fmtCurrency(opt.unit_cost)}</span></div>
            {opt.expiry_savings > 0 && (
              <div className="option-metric" style={{ color: 'var(--green)' }}>
                <span>Expiry Savings</span><span className="val">{fmtCurrency(opt.expiry_savings)}</span>
              </div>
            )}
            {opt.local_premium_pct > 0 && (
              <div className="option-metric" style={{ color: 'var(--yellow)' }}>
                <span>Local Premium</span><span className="val">+{opt.local_premium_pct}%</span>
              </div>
            )}
            {infeasible && (
              <div style={{ marginTop: 6, fontSize: 10, color: 'var(--red)' }}>{opt.reject_reason}</div>
            )}

            {/* Score breakdown */}
            {opt.scores && (
              <div style={{ marginTop: 10, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                {Object.entries(opt.scores).map(([k, v]: [string, any]) => (
                  <div key={k} style={{ marginBottom: 4 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>
                      <span>{k.replace('_', ' ')}</span>
                      <span>{(v * 100).toFixed(0)}%</span>
                    </div>
                    <div className="score-bar">
                      <div className="score-bar-fill" style={{ width: `${v * 100}%` }} />
                    </div>
                  </div>
                ))}
                <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Total Score</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontWeight: 700 }}>
                    {(opt.total_score * 100).toFixed(1)}
                  </span>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ─── Panel F: DACDF ──────────────────────────────────────── */
function DACDFPanel({ data }: { data: any }) {
  const d = data.dacdf || {}
  const alpha = d.alpha || 0.5
  const alphaPct = Math.round(alpha * 100)

  return (
    <>
      <div className="dacdf-panel">
        {/* AI Agent */}
        <div className="agent-box ai">
          <h4>AI Agent (Quantitative)</h4>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
            {d.final_label || d.ai_option}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.5 }}>
            {d.ai_reason}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Confidence: <strong style={{ color: 'var(--accent)' }}>{alphaPct}%</strong>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{d.calibration_note}</div>
        </div>

        {/* Human Agent */}
        <div className="agent-box human">
          <h4>Human / Business Rules</h4>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
            {d.human_option?.replace('_', ' ')}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.5 }}>
            {d.human_reason}
          </div>
          <span className="badge badge-gray" style={{ fontSize: 10 }}>{d.human_source?.replace('_', ' ')}</span>
        </div>
      </div>

      {/* Alpha bar */}
      <div style={{ margin: '16px 0 8px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>
          Confidence weight (alpha): Human rules ← {100 - alphaPct}% / {alphaPct}% → AI model
        </div>
        <div className="alpha-bar">
          <div className="alpha-fill" style={{ width: `${alphaPct}%` }} />
        </div>
        <div className="alpha-labels"><span>0% (rules)</span><span>100% (AI)</span></div>
      </div>

      {/* Fused Recommendation */}
      <div style={{ marginTop: 14, padding: '16px', background: 'var(--green-dim)', border: '1px solid var(--green)', borderRadius: 'var(--radius)', position: 'relative' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--green)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
          Final Recommendation (DACDF Fusion)
        </div>
        <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 6 }}>
          {d.final_label || d.final_option} — {fmtNum(d.final_qty)} units
        </div>
        {d.final_total_cost > 0 && (
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6 }}>
            Estimated cost: {fmtCurrency(d.final_total_cost)} · Lead time: {d.final_lead_time_days}d
            {d.final_source_dc && ` · From: ${d.final_source_dc}`}
          </div>
        )}
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
          {d.agree ? '✓ AI and business rules agree' : `⚡ ${d.consensus_note}`}
        </div>
      </div>
    </>
  )
}

/* ─── Main SKU Detail Page ────────────────────────────────── */
export default function SKUDetailPage() {
  const { dc_id, sku_id } = useParams<{ dc_id: string; sku_id: string }>()
  const router = useRouter()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchSkuDetail(dc_id, sku_id).then(d => { setData(d); setLoading(false) })
  }, [dc_id, sku_id])

  if (loading) return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <div className="loading-wrap" style={{ height: '100vh' }}><div className="spinner" /> Loading SKU analysis…</div>
      </div>
    </div>
  )

  if (!data) return <div className="app-shell"><Sidebar /><div className="main-content"><div className="page-body">SKU not found</div></div></div>

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span style={{ cursor: 'pointer' }} onClick={() => router.push('/dashboard')}>Dashboard</span>
            <span className="crumb-sep">/</span>
            <span style={{ cursor: 'pointer' }} onClick={() => router.push(`/dc/${dc_id}`)}>{dc_id}</span>
            <span className="crumb-sep">/</span>
            <span className="crumb-current">{sku_id}</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <span className={`badge ${critClass(data.criticality)}`}>{data.criticality}</span>
            <span className={`badge badge-${data.health_flag}`}>
              <span className={`dot dot-${data.health_flag}`} />
              {data.health_flag?.toUpperCase()}
            </span>
          </div>
        </div>

        <div className="page-body">
          <div className="page-header">
            <div className="page-title-group">
              <h1>{data.sku_name} <span style={{ fontSize: '1rem', color: 'var(--text-muted)', fontWeight: 400 }}>({sku_id})</span></h1>
              <p>{data.category} · {dc_id} · Analysis date: 2026-08-13</p>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <span className={`trend-chip ${trendClass(data.trend)}`}>{trendIcon(data.trend)} {data.trend}</span>
              <button className="btn btn-secondary" onClick={() => router.push(`/dc/${dc_id}`)}>← Back to {dc_id}</button>
            </div>
          </div>

          <div className="sku-panels">
            {/* A: Demand Forecast */}
            <SectionCard title="Demand Forecast" icon="📈" wide>
              <ForecastPanel data={data} />
            </SectionCard>

            {/* B: Inventory Status */}
            <SectionCard title="Inventory Status" icon="📦">
              <InventoryPanel data={data} />
            </SectionCard>

            {/* C: FEFO / Batches */}
            <SectionCard title="Batch Expiry (FEFO Order)" icon="🧪">
              <FEFOPanel data={data} />
            </SectionCard>

            {/* D: Replenishment Requirement */}
            <SectionCard title="Replenishment Requirement" icon="🔢">
              <RequirementPanel data={data} />
            </SectionCard>

            {/* E: Option Comparison */}
            <SectionCard title="Replenishment Options — Cost Comparison" icon="⚖️" wide>
              <OptionsPanel data={data} />
            </SectionCard>

            {/* F: DACDF */}
            <SectionCard title="DACDF — Dual-Agent Decision Fusion" icon="🤝" wide>
              <DACDFPanel data={data} />
            </SectionCard>
          </div>
        </div>
      </div>
    </div>
  )
}
