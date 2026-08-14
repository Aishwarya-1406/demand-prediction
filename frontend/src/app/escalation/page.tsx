'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import { fetchEscalation, critClass, trendIcon, trendClass, fmtNum, fmtCurrency } from '@/lib/api'

const TIER_META = [
  { tier: 3, label: 'Emergency',           color: 'var(--red)',    bg: 'var(--red-dim)',              icon: '🚨', cadence: '2h',  desc: 'Stockout imminent — Supply Chain Head + emergency sourcing' },
  { tier: 2, label: 'Escalate to Manager', color: 'var(--orange)', bg: 'rgba(227,179,65,0.12)',       icon: '⚠️', cadence: '6h',  desc: 'High-criticality SKU at risk — manager review required' },
  { tier: 1, label: 'Reorder Alert',       color: 'var(--yellow)', bg: 'var(--yellow-dim)',            icon: '📋', cadence: '12h', desc: 'Below reorder point — planner to place order within 24h' },
  { tier: 0, label: 'Monitor',             color: 'var(--green)',  bg: 'var(--green-dim)',             icon: '✅', cadence: '24h', desc: 'Inventory healthy — automated daily review' },
]

const OWNER_AVATAR: Record<string, string> = {
  'Supply Chain Head': '👤',
  'Supply Chain Manager': '👥',
  'DC Planner': '📊',
  'Automated System': '🤖',
}

function TierBadge({ tier }: { tier: number }) {
  const m = TIER_META.find(t => t.tier === tier) || TIER_META[3]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      background: m.bg, color: m.color, whiteSpace: 'nowrap',
    }}>
      {m.icon} {m.label}
    </span>
  )
}

function SummaryTile({ meta, count, active }: { meta: typeof TIER_META[0]; count: number; active: boolean }) {
  return (
    <div style={{
      background: active ? meta.bg : 'var(--bg-card)',
      border: `1px solid ${active ? meta.color : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      padding: '16px 20px',
      cursor: count > 0 ? 'pointer' : 'default',
      transition: 'all 0.15s',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <span style={{ fontSize: 24 }}>{meta.icon}</span>
        <span style={{ fontSize: 32, fontWeight: 800, fontFamily: 'var(--font-mono)', color: count > 0 ? meta.color : 'var(--text-muted)' }}>{count}</span>
      </div>
      <div style={{ fontWeight: 700, fontSize: 13, color: count > 0 ? meta.color : 'var(--text-secondary)' }}>Tier {meta.tier}: {meta.label}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{meta.desc}</div>
      <div style={{ marginTop: 8, fontSize: 11, color: meta.color, fontWeight: 600 }}>⏱ Review every {meta.cadence}</div>
    </div>
  )
}

export default function EscalationPage() {
  const router = useRouter()
  const [data, setData]         = useState<any>(null)
  const [loading, setLoading]   = useState(true)
  const [tierFilter, setTierFilter]   = useState('')
  const [dcFilter, setDcFilter]       = useState('')
  const [critFilter, setCritFilter]   = useState('')
  const [expandedRow, setExpandedRow] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    const params: Record<string, string> = {}
    if (tierFilter) params.tier = tierFilter
    if (dcFilter)   params.dc_id = dcFilter
    if (critFilter) params.criticality = critFilter
    fetchEscalation(params)
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [tierFilter, dcFilter, critFilter])

  useEffect(() => { load() }, [load])

  const rows: any[] = data?.rows || []
  const summary = data?.summary || {}

  const tierColor = (t: number) => TIER_META.find(m => m.tier === t)?.color || 'var(--text-muted)'
  const tierBg    = (t: number) => TIER_META.find(m => m.tier === t)?.bg    || 'var(--bg-card)'
  const tierIcon  = (t: number) => TIER_META.find(m => m.tier === t)?.icon  || '—'

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span style={{ cursor: 'pointer' }} onClick={() => router.push('/dashboard')}>Dashboard</span>
            <span className="crumb-sep">/</span>
            <span className="crumb-current">Escalation & Review Cadence</span>
          </div>
          <div className="topbar-actions">
            <select id="filter-tier" value={tierFilter} onChange={e => setTierFilter(e.target.value)}>
              <option value="">All Tiers</option>
              <option value="3">🚨 Tier 3 — Emergency</option>
              <option value="2">⚠️ Tier 2 — Escalate</option>
              <option value="1">📋 Tier 1 — Reorder</option>
              <option value="0">✅ Tier 0 — Monitor</option>
            </select>
            <select id="filter-dc-esc" value={dcFilter} onChange={e => setDcFilter(e.target.value)}>
              <option value="">All DCs</option>
              {['DC001','DC002','DC003','DC004','DC005'].map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <select id="filter-crit-esc" value={critFilter} onChange={e => setCritFilter(e.target.value)}>
              <option value="">All Criticality</option>
              {['High','Medium','Low'].map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>

        <div className="page-body">
          <div className="page-header">
            <div className="page-title-group">
              <h1>Escalation & Review Cadence</h1>
              <p>4-tier shortage management framework across MedCare Pharma network. Analysis date: 2026-08-13.</p>
            </div>
          </div>

          {/* Summary tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
            {TIER_META.map(m => {
              const countKey = ['tier_0_monitor','tier_1_reorder','tier_2_escalate','tier_3_emergency'][m.tier] as keyof typeof summary
              const count = summary[countKey] ?? 0
              return (
                <div key={m.tier} onClick={() => setTierFilter(tierFilter === String(m.tier) ? '' : String(m.tier))}>
                  <SummaryTile meta={m} count={count} active={tierFilter === String(m.tier)} />
                </div>
              )
            })}
          </div>

          {/* Escalation framework explanation */}
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header">
              <div className="card-title">📋 Review Cadence Framework</div>
            </div>
            <div className="card-body" style={{ padding: '12px 20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                {TIER_META.map(m => (
                  <div key={m.tier} style={{ padding: '12px 14px', background: m.bg, borderRadius: 8, borderLeft: `3px solid ${m.color}` }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: m.color, marginBottom: 4 }}>{m.icon} Tier {m.tier}: {m.label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>{m.desc}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, fontFamily: 'var(--font-mono)', color: m.color }}>Every {m.cadence}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                      Owner: {Object.entries(OWNER_AVATAR).find(([k]) => k.includes(m.label.split(' ')[0]))?.[1] || '📊'}{' '}
                      {m.tier === 3 ? 'Supply Chain Head' : m.tier === 2 ? 'Supply Chain Manager' : m.tier === 1 ? 'DC Planner' : 'Automated System'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Escalation table */}
          {loading ? (
            <div className="loading-wrap"><div className="spinner" /> Loading escalation data…</div>
          ) : (
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  Escalation Register — {rows.length} items
                  {summary.total_flagged > 0 && (
                    <span style={{ marginLeft: 10, fontSize: 11, color: 'var(--yellow)', fontWeight: 400 }}>
                      {summary.total_flagged} require action
                    </span>
                  )}
                </div>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" id="escalation-table">
                  <thead>
                    <tr>
                      <th>Tier</th>
                      <th>DC</th>
                      <th>SKU</th>
                      <th>Priority</th>
                      <th>Days Stock</th>
                      <th>Trend</th>
                      <th>Near Expiry</th>
                      <th>Review Every</th>
                      <th>Owner</th>
                      <th>Next Review</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row: any, i: number) => {
                      const key = `${row.dc_id}-${row.sku_id}`
                      const expanded = expandedRow === key
                      return (
                        <>
                          <tr key={key} id={`esc-row-${row.dc_id}-${row.sku_id}`}
                            style={{ background: expanded ? tierBg(row.escalation_tier) : undefined }}
                            onClick={() => setExpandedRow(expanded ? null : key)}>
                            <td><TierBadge tier={row.escalation_tier} /></td>
                            <td style={{ fontSize: 11, fontWeight: 600 }}>
                              {row.dc_id}
                              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400 }}>{row.dc_name}</div>
                            </td>
                            <td>
                              <div style={{ fontWeight: 600 }}>{row.sku_id}</div>
                              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{row.sku_name}</div>
                            </td>
                            <td><span className={`badge ${critClass(row.criticality)}`}>{row.criticality}</span></td>
                            <td className="num" style={{ color: row.days_of_stock < 3 ? 'var(--red)' : row.days_of_stock < 7 ? 'var(--yellow)' : 'var(--green)' }}>
                              {row.days_of_stock >= 9999 ? '∞' : `${row.days_of_stock?.toFixed(1)}d`}
                            </td>
                            <td><span className={`trend-chip ${trendClass(row.trend)}`}>{trendIcon(row.trend)} {row.trend}</span></td>
                            <td className="num" style={{ color: row.near_expiry_qty > 0 ? 'var(--orange)' : 'inherit' }}>
                              {fmtNum(row.near_expiry_qty)}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: tierColor(row.escalation_tier) }}>
                              {row.escalation_tier === 3 ? '2h' : row.escalation_tier === 2 ? '6h' : row.escalation_tier === 1 ? '12h' : '24h'}
                            </td>
                            <td style={{ fontSize: 12 }}>
                              {OWNER_AVATAR[row.escalation_owner] || '📊'} {row.escalation_owner}
                            </td>
                            <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                              {row.next_review_datetime?.slice(0, 16)}
                            </td>
                            <td>
                              <button className="btn btn-secondary btn-sm"
                                onClick={(e) => { e.stopPropagation(); router.push(`/dc/${row.dc_id}/${row.sku_id}`) }}>
                                View →
                              </button>
                            </td>
                          </tr>
                          {expanded && (
                            <tr key={`${key}-expanded`}>
                              <td colSpan={11} style={{ background: tierBg(row.escalation_tier), padding: '12px 20px' }}>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7, borderLeft: `3px solid ${tierColor(row.escalation_tier)}`, paddingLeft: 12 }}>
                                  <strong style={{ color: 'var(--text-primary)' }}>Recommended Action:</strong> {row.escalation_action}
                                </div>
                                <div style={{ marginTop: 10, display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 12 }}>
                                  <span>AI Action: <strong style={{ color: 'var(--accent)' }}>{row.best_action_label || row.best_action?.replace('_', ' ')}</strong></span>
                                  <span>Review Period: <strong>{row.review_period_days}d ({row.order_frequency})</strong></span>
                                  <span style={{ color: row.frequency_risk === 'critical' ? 'var(--red)' : row.frequency_risk === 'warning' ? 'var(--yellow)' : 'var(--green)' }}>
                                    Frequency Risk: {row.frequency_risk?.toUpperCase()}
                                  </span>
                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      )
                    })}
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
