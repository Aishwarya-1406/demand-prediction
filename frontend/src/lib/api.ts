const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function fetchDCs() {
  const r = await fetch(`${API}/api/dcs`, { cache: 'no-store' })
  return r.json()
}

export async function fetchDCSkus(dcId: string) {
  const r = await fetch(`${API}/api/dcs/${dcId}/skus`, { cache: 'no-store' })
  return r.json()
}

export async function fetchSkuDetail(dcId: string, skuId: string) {
  const r = await fetch(`${API}/api/dcs/${dcId}/skus/${skuId}`, { cache: 'no-store' })
  return r.json()
}

export async function fetchReplenishment(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : ''
  const r = await fetch(`${API}/api/replenishment${qs}`, { cache: 'no-store' })
  return r.json()
}

export async function fetchKPIs() {
  const r = await fetch(`${API}/api/replenishment/kpis`, { cache: 'no-store' })
  return r.json()
}

export async function fetchRules() {
  const r = await fetch(`${API}/api/business-rules`, { cache: 'no-store' })
  return r.json()
}

export async function retrain() {
  const r = await fetch(`${API}/api/retrain`, { method: 'POST', cache: 'no-store' })
  return r.json()
}

export async function fetchEscalation(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : ''
  const r = await fetch(`${API}/api/escalation${qs}`, { cache: 'no-store' })
  return r.json()
}

export async function fetchSkuEscalation(dcId: string, skuId: string) {
  const r = await fetch(`${API}/api/escalation/${dcId}/${skuId}`, { cache: 'no-store' })
  return r.json()
}


// Helpers
export function healthClass(flag: string) {
  if (flag === 'red') return 'badge-red'
  if (flag === 'yellow') return 'badge-yellow'
  return 'badge-green'
}

export function critClass(c: string) {
  if (c === 'High') return 'crit-high'
  if (c === 'Medium') return 'crit-medium'
  return 'crit-low'
}

export function trendClass(t: string) {
  const map: Record<string, string> = {
    rising: 'trend-rising', falling: 'trend-falling',
    stable: 'trend-stable', surge: 'trend-surge', seasonal: 'trend-seasonal',
  }
  return map[t] || 'trend-stable'
}

export function trendIcon(t: string) {
  const map: Record<string, string> = {
    rising: '↑', falling: '↓', stable: '→', surge: '⚡', seasonal: '❄',
  }
  return map[t] || '→'
}

export function fmtCurrency(n: number) {
  if (!n) return '₹0'
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`
  return `₹${n}`
}

export function fmtNum(n: number) {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString()
}
