import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

function fmtWhen(v) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

export default function AccountDeletionsAdmin() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending')
  const [detail, setDetail] = useState(null)
  const [completeId, setCompleteId] = useState(null)
  const [confirmText, setConfirmText] = useState('')
  const [adminNotes, setAdminNotes] = useState('')

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '200', status_filter: statusFilter || 'all' })
    const res = await apiFetch(`/admin/account-deletions?${params.toString()}`)
    setRows(Array.isArray(res?.items) ? res.items : [])
  }, [statusFilter])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const pendingCount = useMemo(() => rows.filter((r) => r.status === 'pending').length, [rows])

  const openDetail = async (id) => {
    setError('')
    try {
      const data = await apiFetch(`/admin/account-deletions/${encodeURIComponent(id)}`)
      setDetail(data)
    } catch (e) {
      setError(e?.message || 'Could not load detail')
    }
  }

  const completeDeletion = async () => {
    if (!completeId) return
    if (confirmText.trim().toUpperCase() !== 'DELETE') {
      window.alert('Type DELETE to confirm')
      return
    }
    setBusy(completeId)
    setError('')
    try {
      await apiFetch(`/admin/account-deletions/${encodeURIComponent(completeId)}/complete`, {
        method: 'POST',
        body: JSON.stringify({ confirm: 'DELETE', admin_notes: adminNotes.trim() || undefined }),
      })
      setCompleteId(null)
      setConfirmText('')
      setAdminNotes('')
      setDetail(null)
      await load()
    } catch (e) {
      setError(e?.message || 'Complete failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Account deletion requests</h1>
          <p>Review user-requested account deletions, view activity, and complete archival.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error ? (
        <div className="note" style={{ marginBottom: 16, borderColor: 'rgba(220,38,38,0.35)' }}>
          {error}
        </div>
      ) : null}

      <div className="grid-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="cardBody">
            <div className="muted" style={{ fontSize: 12 }}>Pending</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{pendingCount}</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardBody" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="muted" style={{ fontSize: 13 }}>Status</label>
          <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 200 }}>
            <option value="pending">Pending</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
            <option value="all">All</option>
          </select>
        </div>
      </div>

      <div className="card">
        <div className="cardBody tableWrap">
          <table className="table">
            <thead>
              <tr>
                <th>Requested</th>
                <th>User</th>
                <th>Organisation</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="muted">Loading…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={5} className="muted">No deletion requests.</td></tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id}>
                    <td>{fmtWhen(row.requested_at)}</td>
                    <td>{row.requested_by_email}</td>
                    <td>
                      <div>{row.org_name || '—'}</div>
                      <div className="muted" style={{ fontSize: 11 }}>{row.org_id}</div>
                    </td>
                    <td><span className={`pill ${row.status === 'pending' ? 'p-amber' : row.status === 'completed' ? 'p-green' : ''}`}>{row.status}</span></td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <button type="button" className="btn soft xs" onClick={() => openDetail(row.id)}>Activity</button>
                        <button
                          type="button"
                          className="btn soft xs"
                          onClick={() => {
                            localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id)
                            navigate('/organisations/all-users')
                          }}
                        >
                          OCC
                        </button>
                        {row.status === 'pending' ? (
                          <button type="button" className="btn primary xs" onClick={() => { setCompleteId(row.id); setConfirmText(''); setAdminNotes('') }}>
                            Complete deletion
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {detail ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="cardHead" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Activity — {detail.requested_by_email}</h3>
            <button type="button" className="btn soft xs" onClick={() => setDetail(null)}>Close</button>
          </div>
          <div className="cardBody">
            {(detail.activity || []).length === 0 ? (
              <p className="muted">No deletion activity logged.</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
                {(detail.activity || []).map((ev) => (
                  <li key={ev.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ fontWeight: 600 }}>{ev.action || ev.event_type}</div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {[ev.actor_email, ev.detail, fmtWhen(ev.created_at)].filter(Boolean).join(' · ')}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}

      {completeId ? (
        <div className="card" style={{ marginTop: 16, borderColor: 'rgba(220,38,38,0.35)' }}>
          <div className="cardHead"><h3 style={{ color: 'var(--red)' }}>Complete account deletion</h3></div>
          <div className="cardBody" style={{ display: 'grid', gap: 12, maxWidth: 480 }}>
            <p className="muted" style={{ fontSize: 13 }}>
              Archives the organisation, anonymizes PII, and retains invoices/audit records. Stop running campaigns first.
            </p>
            <label className="field">
              <span className="fieldLabel">Admin notes (optional)</span>
              <textarea className="input" rows={2} value={adminNotes} onChange={(e) => setAdminNotes(e.target.value)} />
            </label>
            <label className="field">
              <span className="fieldLabel">Type DELETE to confirm</span>
              <input className="input" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn primary" disabled={busy === completeId} onClick={() => void completeDeletion()}>
                {busy === completeId ? 'Processing…' : 'Confirm deletion'}
              </button>
              <button type="button" className="btn soft" onClick={() => setCompleteId(null)}>Cancel</button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
