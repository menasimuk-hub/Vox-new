import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAbuuExternalEvents } from '../../lib/abuuApi'
import { dateText } from '../../lib/abuuAdminUtils'

const STATUS_OPTIONS = ['', 'processed', 'duplicate', 'failed', 'ignored']

export default function AbuuEventLog() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const load = useCallback(async () => {
    const data = await fetchAbuuExternalEvents({
      status: statusFilter || undefined,
      limit: 200,
    })
    setRows(Array.isArray(data) ? data : [])
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

  return (
    <div className='card'>
      <div className='cardBody'>
        <div className='billingPageToolbar'>
          <label className='billingFilter'>
            Status
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUS_OPTIONS.map((s) => (
                <option key={s || 'all'} value={s}>
                  {s || 'All'}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error ? <p className='formError'>{error}</p> : null}
        {loading ? (
          <p className='muted'>Loading events…</p>
        ) : (
          <div className='tableWrap'>
            <table className='table billingTable'>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Order</th>
                  <th>Key</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{dateText(row.created_at)}</td>
                    <td>{row.source}</td>
                    <td>{row.event_type}</td>
                    <td>
                      <span className={`pill${row.status === 'failed' ? ' warn' : ''}`}>{row.status}</span>
                    </td>
                    <td>
                      {row.order_id ? (
                        <Link to={`/abuu/orders?order=${row.order_id}`}>
                          <code>{row.order_id.slice(0, 8)}</code>
                        </Link>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className='muted small'>{row.idempotency_key}</td>
                  </tr>
                ))}
                {!rows.length ? (
                  <tr>
                    <td colSpan={6} className='muted'>
                      No events for this filter.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
