'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function LoginPage() {
  const router = useRouter()
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setErr('')
    setTimeout(() => {
      if (user === 'admin' && pass === 'medcare2026') {
        sessionStorage.setItem('auth', '1')
        router.push('/dashboard')
      } else {
        setErr('Invalid credentials. Use admin / medcare2026')
        setLoading(false)
      }
    }, 400)
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-mark">M</div>
          <div>
            <div className="login-logo-text">MedCare Pharma</div>
            <div className="login-logo-sub">Supply Chain Intelligence Platform</div>
          </div>
        </div>

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label className="form-label" htmlFor="username">Username</label>
            <input id="username" className="form-input" type="text" value={user}
              onChange={e => setUser(e.target.value)} placeholder="admin" autoComplete="username" />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="password">Password</label>
            <input id="password" className="form-input" type="password" value={pass}
              onChange={e => setPass(e.target.value)} placeholder="medcare2026" autoComplete="current-password" />
          </div>
          {err && <div className="form-error">{err}</div>}
          <button type="submit" className="btn btn-primary" id="login-btn"
            style={{ width: '100%', justifyContent: 'center', marginTop: 16 }}
            disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <div style={{ marginTop: 20, padding: 12, background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', fontSize: 12, color: 'var(--text-muted)' }}>
          Demo: <strong style={{ color: 'var(--text-secondary)' }}>admin</strong> / <strong style={{ color: 'var(--text-secondary)' }}>medcare2026</strong>
        </div>
      </div>
    </div>
  )
}
