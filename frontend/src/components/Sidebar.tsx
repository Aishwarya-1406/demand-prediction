'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

const navItems = [
  { href: '/dashboard',   label: 'Dashboard',    icon: '◉' },
  { href: '/replenishment', label: 'Replenishment', icon: '⬡' },
  { href: '/escalation',  label: 'Escalation',   icon: '🚨' },
]


const dcItems = [
  { id: 'DC001', name: 'Mumbai', icon: '●' },
  { id: 'DC002', name: 'Delhi', icon: '●' },
  { id: 'DC003', name: 'Bangalore', icon: '●' },
  { id: 'DC004', name: 'Kolkata', icon: '●' },
  { id: 'DC005', name: 'Chennai', icon: '●' },
]

export default function Sidebar() {
  const path = usePathname()
  const router = useRouter()

  useEffect(() => {
    if (!sessionStorage.getItem('auth')) router.push('/')
  }, [router])

  const logout = () => {
    sessionStorage.removeItem('auth')
    router.push('/')
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">M</div>
        <div>
          <div className="logo-text">MedCare Pharma</div>
          <div className="logo-sub">Supply Intelligence</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Overview</div>
        {navItems.map(n => (
          <Link key={n.href} href={n.href}
            className={`nav-link ${path === n.href ? 'active' : ''}`}>
            <span className="nav-icon">{n.icon}</span>
            {n.label}
          </Link>
        ))}

        <div className="nav-section-label" style={{ marginTop: 12 }}>Distribution Centers</div>
        {dcItems.map(dc => (
          <Link key={dc.id} href={`/dc/${dc.id}`}
            className={`nav-link ${path.startsWith(`/dc/${dc.id}`) ? 'active' : ''}`}>
            <span className="nav-icon" style={{ fontSize: 8 }}>{dc.icon}</span>
            <span>{dc.name} DC</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)' }}>{dc.id}</span>
          </Link>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>Admin</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Planner</div>
        </div>
        <button onClick={logout} className="btn btn-secondary btn-sm" id="logout-btn">
          Sign out
        </button>
      </div>
    </aside>
  )
}
