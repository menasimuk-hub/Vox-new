import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const PAGE_SIZE = 20

export default function ComplianceOptOuts() {
  const [orgs, setOrgs] = useState([])
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const [orgId, setOrgId] = useState('')
  const [phone, setPhone] = useState('')
  const [reason, setReason] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const [addOrgId, setAddOrgId] = useState('')
  const [addPhone, setAddPhone] = useState('')
  const [addName, setAddName] = useState('')
  const [addReason, setAddReason] = useState('Manual admin add')
  const [saving, setSaving] = useState(false)

  const loadOrgs = useCallback(async () => {
    const data = await apiFetch('/admin/organisations?limit=200')
    const list = Array.isArray(data?.items) ? data.items : []
    setOrgs(list)
    setAddOrgId((prev) => prev || String(list[0]?.id || ''))
  }, [])

  const loadList = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(PAGE_SIZE))
      if (orgId) params.set('org_id', orgId)
      if (phone.trim()) params.set('phone', phone.trim())
      if (reason.trim()) params.set('reason', reason.trim())
      if (fromDate) params.set('from_date', `${fromDate}T00:00:00`)
      if (toDate) params.set('to_date', `${toDate}T23:59:59`)
      const data = await apiFetch(`/admin/opt-outs?${params.toString()}`)
      setItems(Array.isArray(data?.items) ? data.items : [])
      setTotal(Number(data?.total) || 0)
      setPages(Number(data?.pages) || 1)
    } catch (e) {
      setError(e?.message || 'Could not load opt-out list')
    } finally {
      setLoading(false)
    }
  }, [page, orgId, phone, reason, fromDate, toDate])

  useEffect(() => {
    loadOrgs().catch((e) => setError(e?.message || 'Could not load organisations'))
  }, [loadOrgs])

  useEffect(() => {
    void loadList()
  }, [loadList])

  const onSearch = (e) => {
    e.preventDefault()
    setPage(1)
    void loadList()
  }

  const onAdd = async (e) => {
    e.preventDefault()
    if (!addOrgId || !addPhone.trim()) {
      setError('Organisation and phone are required')
      return
    }
    setSaving(true)
    setError('')
    setMsg('')
    try {
      await apiFetch('/admin/opt-outs', {
        method: 'POST',
        body: JSON.stringify({
          org_id: addOrgId,
          phone: addPhone.trim(),
          name: addName.trim() || undefined,
          reason: addReason.trim() || undefined,
        }),
      })
      setMsg('Number added to opt-out list')
      setAddPhone('')
      setAddName('')
      setPage(1)
      await loadList()
    } catch (err) {
      setError(err?.message || 'Could not add opt-out')
    } finally {
      setSaving(false)
    }
  }

  const onRemove = async (id) => {
    if (!window.confirm('Remove this number from the opt-out list?')) return
    setError('')
    try {
      await apiFetch(`/admin/opt-outs/${encodeURIComponent(id)}`, { method: 'DELETE' })
      setMsg('Removed from opt-out list')
      await loadList()
    } catch (err) {
      setError(err?.message || 'Could not remove opt-out')
    }
  }

  const fmtDate = (raw) => {
    if (!raw) return '—'
    try {
      return new Date(raw).toLocaleString()
    } catch {
      return String(raw)
    }
  }

  return (
    <div className="page">
      <div className="pageHead">
        <div>
          <div className="breadcrumb">
            <Link to="/compliance/consent">Compliance</Link> / STOP opt-out list
          </div>
          <h1>STOP / opt-out list</h1>
          <p className="muted">Platform-wide numbers that must not be called or messaged (all organisations).</p>
        </div>
      </div>

      {error ? <div className="alert error">{error}</div> : null}
      {msg ? <div className="alert success">{msg}</div> : null}

      <form className="card" onSubmit={onSearch} style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Filters</h3>
        <div className="grid4" style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
          <label>
            <span className="label">Organisation</span>
            <select className="input" value={orgId} onChange={(e) => { setOrgId(e.target.value); setPage(1) }}>
              <option value="">All organisations</option>
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.name || o.id}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Phone</span>
            <input className="input" placeholder="+4477…" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <label>
            <span className="label">Reason</span>
            <input className="input" placeholder="whatsapp_keyword…" value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <label>
            <span className="label">From</span>
            <input className="input" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          </label>
          <label>
            <span className="label">To</span>
            <input className="input" type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
          </label>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <button type="submit" className="btn primary">Search</button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setOrgId('')
              setPhone('')
              setReason('')
              setFromDate('')
              setToDate('')
              setPage(1)
            }}
          >
            Clear
          </button>
        </div>
      </form>

      <form className="card" onSubmit={onAdd} style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Add number</h3>
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
          <label>
            <span className="label">Organisation</span>
            <select className="input" value={addOrgId} onChange={(e) => setAddOrgId(e.target.value)} required>
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.name || o.id}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Phone (E.164)</span>
            <input className="input" placeholder="+447700900123" value={addPhone} onChange={(e) => setAddPhone(e.target.value)} required />
          </label>
          <label>
            <span className="label">Name</span>
            <input className="input" value={addName} onChange={(e) => setAddName(e.target.value)} />
          </label>
          <label>
            <span className="label">Reason</span>
            <input className="input" value={addReason} onChange={(e) => setAddReason(e.target.value)} />
          </label>
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="submit" className="btn primary" disabled={saving}>{saving ? 'Adding…' : 'Add to list'}</button>
        </div>
      </form>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Opt-outs ({total})</h3>
          <span className="muted">Page {page} of {pages} · {PAGE_SIZE} per page</span>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div className="tableWrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Phone</th>
                  <th>Name</th>
                  <th>Organisation</th>
                  <th>Reason</th>
                  <th>Added</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="muted">No opt-outs match these filters.</td>
                  </tr>
                ) : (
                  items.map((row) => (
                    <tr key={row.id}>
                      <td><code>{row.phone_e164 || row.phone}</code></td>
                      <td>{row.contact_name || row.name || '—'}</td>
                      <td>{row.org_name || row.org_id || '—'}</td>
                      <td>{row.reason || '—'}</td>
                      <td>{fmtDate(row.created_at)}</td>
                      <td>
                        <button type="button" className="btn danger sm" onClick={() => void onRemove(row.id)}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            Previous
          </button>
          <button type="button" className="btn" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
