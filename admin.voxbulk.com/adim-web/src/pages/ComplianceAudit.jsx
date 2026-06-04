import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

export default function ComplianceAudit() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const qs = filter ? `?limit=200&event_type=${encodeURIComponent(filter)}` : '?limit=200'
      const data = await apiFetch(`/admin/compliance/audit${qs}`)
      setEvents(Array.isArray(data?.events) ? data.events : [])
    } catch (e) {
      setError(e?.message || 'Could not load audit log')
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to="/compliance/consent" style={{ color: 'var(--grn)' }}>Compliance</Link> / Audit
          </div>
          <h1>Compliance audit log</h1>
          <p className="pageLead">
            Template changes, opt-outs, send blocks, workflow launches, and retention passes.
          </p>
        </div>
      </div>

      {error ? <div className="alert error"><strong>{error}</strong></div> : null}

      <div className="card">
        <div className="cardHead" style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <h2>Events</h2>
          <input
            className="input"
            style={{ maxWidth: 280 }}
            placeholder="Filter by event_type"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <button type="button" className="btn sm" onClick={load}>Refresh</button>
        </div>
        <div className="cardBody">
          {loading ? (
            <p className="muted">Loading…</p>
          ) : (
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Type</th>
                    <th>Org</th>
                    <th>Order</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.id}>
                      <td>{ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}</td>
                      <td><code>{ev.event_type}</code></td>
                      <td className="muted">{ev.org_id || '—'}</td>
                      <td className="muted">{ev.order_id || '—'}</td>
                      <td><pre className="waSurveyFeedbackDetail" style={{ margin: 0 }}>{JSON.stringify(ev.detail || {}, null, 0)}</pre></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
