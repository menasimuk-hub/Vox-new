import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const ROLES = [
  { value: 'superadmin', label: 'Superadmin (full access, can manage admins)' },
  { value: 'accountant', label: 'Accountant (billing & organisations — no integrations / admin CRUD)' },
  { value: 'marketing', label: 'Marketing (email / templates — no integrations or billing sinks)' },
]

export default function AdminUserEdit() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('marketing')
  const [active, setActive] = useState(true)
  const [newPassword, setNewPassword] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setErr('')
      try {
        const rows = await apiFetch('/admin/admin-users')
        const row = Array.isArray(rows) ? rows.find((r) => r.id === id) : null
        if (!row) throw new Error('Admin user not found')
        if (cancelled) return
        setEmail(row.email || '')
        setRole(String(row.role || 'marketing').toLowerCase())
        setActive(!!row.is_active)
      } catch (e) {
        if (!cancelled) setErr(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [id])

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      const body = {
        role: String(role || '').trim().toLowerCase(),
        is_active: Boolean(active),
      }
      const pw = String(newPassword || '').trim()
      if (pw.length > 0) {
        body.password = pw
      }
      await apiFetch(`/admin/admin-users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) })
      navigate('/admin/users')
    } catch (e2) {
      setErr(e2?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Edit platform admin</h1>
          <p>
            Updates the <strong>platform</strong> admin account backing this login (not clinic / invite users listed on an
            organisation).
          </p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={() => navigate('/admin/users')}>
            Back to list
          </button>
        </div>
      </div>

      <div className='pageShell' style={{ margin: '0 auto', width: '100%', maxWidth: 720 }}>
        <div className='card'>
          <div className='cardHead'>
            <h3>{email || id}</h3>
            <span className='pill p-cyan'>Superadmin-only</span>
          </div>
          <div className='cardBody'>
            {err ? (
              <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>
                {err}
              </div>
            ) : null}
            {loading ? (
              <div className='note'>Loading…</div>
            ) : (
              <form onSubmit={save} className='stack' style={{ gap: 12 }}>
                <label className='label'>Email</label>
                <input className='input' value={email} readOnly />

                <label className='label'>Platform role</label>
                <select className='input' value={role} onChange={(e) => setRole(e.target.value)}>
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>

                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                  <input type='checkbox' checked={active} onChange={(e) => setActive(e.target.checked)} />
                  <span className='muted'>Active (can sign in)</span>
                </label>

                <div style={{ display: 'grid', gap: 6 }}>
                  <label className='label'>New password (optional)</label>
                  <input
                    className='input'
                    type='password'
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder='Leave blank to keep current password'
                    minLength={6}
                    autoComplete='new-password'
                  />
                </div>

                <div className='actions' style={{ marginTop: 6 }}>
                  <button className='btn primary' disabled={saving}>
                    {saving ? 'Saving…' : 'Save changes'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
