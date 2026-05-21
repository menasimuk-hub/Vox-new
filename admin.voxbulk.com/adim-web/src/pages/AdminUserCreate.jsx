import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const ROLES = [
  { value: 'superadmin', label: 'Superadmin — full console + manage platform admins' },
  { value: 'accountant', label: 'Accountant — billing & organisations (no integrations, secrets, admin CRUD)' },
  { value: 'marketing', label: 'Marketing — SMTP & templates (no billing sinks or integrations)' },
]

export default function AdminUserCreate() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('marketing')
  const [isActive, setIsActive] = useState(true)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      const res = await apiFetch('/admin/admin-users', {
        method: 'POST',
        body: JSON.stringify({
          email: String(email || '').trim(),
          password: String(password || ''),
          role: String(role || '').trim().toLowerCase(),
          is_active: Boolean(isActive),
          is_superuser: String(role || '').trim().toLowerCase() === 'superadmin',
        }),
      })
      setMsg(`Created platform admin for ${res?.email || email}. Sign in via the same public VOXBULK login URL using this email and password.`)
      setEmail('')
      setPassword('')
    } catch (e2) {
      setErr(e2?.message || 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Add platform admin</h1>
          <p>
            Creates a login for internal VOXBULK operators — not clinic staff invited to an organisation (those live under{' '}
            <strong>Organisations → Users</strong> once you pick a clinic).
          </p>
        </div>
        <div className='actions'>
          <Link className='btn soft' to='/platform/users'>
            Back to list
          </Link>
        </div>
      </div>

      <div className='pageShell' style={{ margin: '0 auto', width: '100%', maxWidth: 720 }}>
        <div className='card'>
          <div className='cardHead'>
            <h3>New platform admin</h3>
            <span className='pill p-cyan'>Superadmin-only</span>
          </div>
          <div className='cardBody'>
            {err ? (
              <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>
                {err}
              </div>
            ) : null}
            {msg ? <div className='note'>{msg}</div> : null}

            <form onSubmit={submit} className='stack' style={{ gap: 12 }}>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Email</label>
                <input
                  className='input'
                  type='email'
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder='ops@yourcompany.com'
                  required
                />
              </div>

              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Temporary password</label>
                <input
                  className='input'
                  type='password'
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder='Min 6 characters'
                  required
                  minLength={6}
                />
              </div>

              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Platform role</label>
                <select className='input' value={role} onChange={(e) => setRole(e.target.value)}>
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                <input type='checkbox' checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                <span className='muted'>Active (can sign in)</span>
              </label>

              <div className='actions' style={{ marginTop: 6 }}>
                <button className='btn primary' disabled={busy}>
                  {busy ? 'Creating…' : 'Create platform admin'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </>
  )
}
