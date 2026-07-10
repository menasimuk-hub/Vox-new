import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { useAdminProfile } from '../context/AdminProfileContext'

export default function AdminUsers() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [rows, setRows] = useState([])
  const { profile } = useAdminProfile()
  const canManage = !!profile?.can_manage_admin_users

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/admin-users')
      setRows(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e?.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const del = async (id) => {
    if (!canManage) return
    const ok = window.confirm('Disable and remove this platform admin login? Organisation users on customer accounts are unaffected.')
    if (!ok) return
    try {
      await apiFetch(`/admin/admin-users/${encodeURIComponent(id)}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(e?.message || 'Delete failed')
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Platform admin users</h1>
          <p>
            Separate from <strong>organisation users</strong> (managed under each organisation). Platform admins manage VOXBULK internally
            (billing, onboarding, integrations, SMTP/templates). Only <strong>superadmin</strong> can create/delete these users.
          </p>
        </div>
        <div className='actions'>
          <Link className='btn soft' to='/platform/users/new'>
            Add platform admin
          </Link>
          <button className='btn' onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      <div className='pageShell' style={{ margin: '0 auto', width: '100%', maxWidth: 980 }}>
        <div className='card'>
          <div className='cardHead'>
            <h3>Users</h3>
            <span className='pill p-cyan'>{rows.length} total</span>
          </div>
          <div className='cardBody'>
            {error ? (
              <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>
                {error}
              </div>
            ) : null}
            {loading ? <div className='note'>Loading…</div> : null}
            {!loading && (
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Status</th>
                      <th>Superadmin</th>
                      <th>Role</th>
                      <th>Created</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id}>
                        <td>{r.email}</td>
                        <td>{r.is_active ? 'Active' : 'Disabled'}</td>
                        <td>{r.is_superuser ? 'Yes' : 'No'}</td>
                        <td className='muted'>{r.role || '-'}</td>
                        <td className='muted'>{r.created_at ? new Date(r.created_at).toLocaleString() : '-'}</td>
                        <td style={{ textAlign: 'right' }}>
                          {canManage ? (
                            <>
                              <Link className='btn soft' to={`/platform/users/${encodeURIComponent(r.id)}/edit`} style={{ marginRight: 8 }}>
                                Edit
                              </Link>
                              <button className='btn soft' onClick={() => del(r.id)}>
                                Delete
                              </button>
                            </>
                          ) : (
                            <span className='muted'>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                    {!rows.length ? (
                      <tr>
                        <td colSpan={6} className='muted'>
                          No admin users found.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

