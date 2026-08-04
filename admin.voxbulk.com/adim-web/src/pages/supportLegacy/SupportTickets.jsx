import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const STATUSES = ['', 'open', 'pending', 'closed']
const CATEGORIES = ['', 'technical', 'invoices', 'pre-sale']

function dt(v) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

function Badge({ value }) {
  const v = String(value || '').toLowerCase()
  const cls = v === 'closed' ? 'p-green' : v === 'pending' ? 'p-amber' : 'p-cyan'
  return <span className={`pill ${cls}`}>{value || '—'}</span>
}

export default function SupportTickets() {
  const [tickets, setTickets] = useState([])
  const [kpis, setKpis] = useState(null)
  const [admins, setAdmins] = useState([])
  const [filters, setFilters] = useState({ status: '', category: '', assigned: '', search: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const qs = new URLSearchParams()
      if (filters.status) qs.set('status_filter', filters.status)
      if (filters.category) qs.set('category', filters.category)
      if (filters.assigned) qs.set('assigned_admin_user_id', filters.assigned)
      if (filters.search.trim()) qs.set('search', filters.search.trim())
      const [rows, stats, adminsRows] = await Promise.all([
        apiFetch(`/admin/support/tickets?${qs.toString()}`),
        apiFetch('/admin/support/kpis'),
        apiFetch('/admin/support/admins').catch(() => []),
      ])
      setTickets(Array.isArray(rows) ? rows : [])
      setKpis(stats || null)
      setAdmins(Array.isArray(adminsRows) ? adminsRows : [])
    } catch (e) {
      setError(e?.message || 'Could not load tickets')
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Support Tickets</h1>
          <p>Native VOXBULK support inbox with tenant-safe ticket threads, replies, status, and assignment.</p>
        </div>
        <div className="actions">
          <button className="btn soft" onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
        </div>
      </div>

      {error ? <div className="card" style={{ marginBottom: 16, borderColor: '#fecaca' }}><div className="cardBody" style={{ color: '#b91c1c' }}>{error}</div></div> : null}

      <div className="grid-4" style={{ marginBottom: 16 }}>
        {[
          ['Open', kpis?.total_open ?? 0, '#2563EB'],
          ['Pending', kpis?.total_pending ?? 0, '#F97316'],
          ['Closed', kpis?.total_closed ?? 0, '#16A34A'],
          ['Unassigned', kpis?.unassigned ?? 0, '#64748B'],
        ].map(([label, value, color]) => <div key={label} className="card stat" style={{ '--accent': color }}><div className="muted">{label}</div><div className="statValue">{value}</div></div>)}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardBody filters">
          <select className="input" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{s || 'All statuses'}</option>)}</select>
          <select className="input" value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>{CATEGORIES.map((c) => <option key={c} value={c}>{c || 'All categories'}</option>)}</select>
          <select className="input" value={filters.assigned} onChange={(e) => setFilters({ ...filters, assigned: e.target.value })}><option value="">All assignees</option><option value="unassigned">Unassigned</option>{admins.map((a) => <option key={a.id} value={a.id}>{a.email}</option>)}</select>
          <input className="input" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} placeholder="Search ref or subject…" />
        </div>
      </div>

      <div className="grid-12">
        <div className="span-12 card">
          <div className="cardHead"><h3>Ticket list</h3><span className="pill p-cyan">{tickets.length}</span></div>
          <div className="cardBody tableWrap">
            <table className="table"><thead><tr><th>Ref</th><th>Organisation</th><th>Subject</th><th>Category</th><th>Status</th><th>Assigned</th><th>Last activity</th></tr></thead><tbody>
              {tickets.length ? tickets.map((t) => <tr key={t.id} onClick={() => navigate(`/support/tickets/${t.id}`)} style={{ cursor: 'pointer' }}><td>{t.admin_unread ? <strong>{t.public_ref}</strong> : t.public_ref}</td><td>{t.organisation_name || '—'}</td><td>{t.subject}</td><td><Badge value={t.category} /></td><td><Badge value={t.status} /></td><td>{t.assigned_admin_email || 'Unassigned'}</td><td>{dt(t.last_message_at)}</td></tr>) : <tr><td colSpan="7">No tickets match these filters.</td></tr>}
            </tbody></table>
          </div>
        </div>
      </div>
    </>
  )
}

