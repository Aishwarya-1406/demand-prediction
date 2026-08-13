'use client'
import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import { fetchDCSkus, critClass, trendClass, trendIcon, fmtNum, fmtCurrency } from '@/lib/api'

const HEALTH_COLOR: Record<string, string> = { red: 'var(--red)', yellow: 'var(--yellow)', green: 'var(--green)' }

export default function DCDetailPage() {
  const { dc_id } = useParams<{ dc_id: string }>()
  const router = useRouter()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('health_flag')
  const [filter, setFilter] = useState('')

  useEffect(() => {
    fetchDCSkus(dc_id).then(d => { setData(d); setLoading(false) })
  }, [dc_id])

  const skus: any[] = data?.skus || []
  const filtered = skus.filter(s =>
    s.sku_name?.toLowerCase().includes(filter.toLowerCase()) ||
    s.sku_id?.toLowerCase().includes(filter.toLowerCase()) ||
    s.criticality?.toLowerCase().includes(filter.toLowerCase())
  )

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span onClick={() => router.push('/dashboard')} style={{ cursor: 'pointer' }}>Dashboard</span>
            <span className="crumb-sep">/</span>
            <span className="crumb-current">{data?.dc_summary?.dc_name || dc_id}</span>
          </div>
          <div className="topbar-actions">
            <input id="sku-search" placeholder="Search SKUs…" value={filter}
              onChange={e => setFilter(e.target.value)}
              style={{ width: 200 }} />
          </div>
        </div>

        <div className="page-body">
          <div className="page-header">
            <div className="page-title-group">
              <h1>{data?.dc_summary?.dc_name || dc_id}</h1>
              <p>{data?.dc_summary?.city} · {data?.dc_summary?.region} Region · 15 SKUs tracked</p>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              {['red', 'yellow', 'green'].map(h => (
                <span key={h} className={`badge badge-${h}`} style={{ cursor: 'pointer' }}
                  onClick={() => setFilter(h === filter ? '' : h)}>
                  {h === 'red' ? 'At Risk' : h === 'yellow' ? 'Reorder' : 'Healthy'}
                  {' '}({skus.filter(s => s.health_flag === h).length})
                </span>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="loading-wrap"><div className="spinner" /> Loading SKUs…</div>
          ) : (
            <div className="card" style={{ overflow: 'hidden' }}>
              <div className="card-header">
                <div className="card-title">SKU Inventory Status</div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{filtered.length} SKUs</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" id="sku-table">
                  <thead>
                    <tr>
                      {[
                        ['sku_id', 'SKU'], ['criticality', 'Priority'], ['health_flag', 'Status'],
                        ['usable_inventory', 'Usable Inv'], ['days_of_stock', 'Days Stock'],
                        ['trend', 'Trend'], ['near_expiry_qty', 'Near Expiry'],
                        ['replenishment_requirement', 'Replen. Req'], ['best_action_label', 'AI Action'],
                        ['mape', 'MAPE %'],
                      ].map(([col, label]) => (
                        <th key={col} onClick={() => setSortCol(col)}
                          style={{ cursor: 'pointer' }}>
                          {label} {sortCol === col ? '↑' : ''}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((sku: any) => (
                      <tr key={sku.sku_id} id={`row-${sku.sku_id}`}
                        onClick={() => router.push(`/dc/${dc_id}/${sku.sku_id}`)}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{sku.sku_id}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sku.sku_name}</div>
                        </td>
                        <td>
                          <span className={`badge ${critClass(sku.criticality)}`}>{sku.criticality}</span>
                        </td>
                        <td>
                          <span className={`badge badge-${sku.health_flag}`}>
                            <span className={`dot dot-${sku.health_flag}`} />
                            {sku.health_flag === 'red' ? 'At Risk' : sku.health_flag === 'yellow' ? 'Reorder' : 'OK'}
                          </span>
                        </td>
                        <td className="num" style={{ color: HEALTH_COLOR[sku.health_flag] }}>
                          {fmtNum(sku.usable_inventory)}
                        </td>
                        <td className="num" style={{ color: sku.days_of_stock < 7 ? 'var(--red)' : sku.days_of_stock < 14 ? 'var(--yellow)' : 'inherit' }}>
                          {sku.days_of_stock === 999 ? '∞' : sku.days_of_stock?.toFixed(1)}d
                        </td>
                        <td>
                          <span className={`trend-chip ${trendClass(sku.trend)}`}>
                            {trendIcon(sku.trend)} {sku.trend}
                          </span>
                        </td>
                        <td className="num" style={{ color: sku.near_expiry_qty > 0 ? 'var(--orange)' : 'inherit' }}>
                          {fmtNum(sku.near_expiry_qty)}
                        </td>
                        <td className="num">{fmtNum(sku.replenishment_requirement)}</td>
                        <td>
                          <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
                            {sku.best_action_label}
                          </span>
                        </td>
                        <td className="num" style={{ color: 'var(--text-muted)' }}>
                          {sku.mape != null ? `${sku.mape.toFixed(1)}%` : '—'}
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
