import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { adminOrderViewPath } from '../lib/serviceOrderAdmin'

export default function ServiceOrdersAdmin() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = useCallback(async () => {
    setError('')
    const rows = await apiFetch('/admin/platform-services/orders?payment_status=pending_approval')
    setOrders(Array.isArray(rows) ? rows : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load orders')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  useEffect(() => {
    const orderId = searchParams.get('order')
    if (!orderId) return
    let cancelled = false
    ;(async () => {
      try {
        const row = await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}`)
        if (!cancelled) navigate(adminOrderViewPath(row), { replace: true })
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not open order detail')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [searchParams, navigate])

  const approve = async (id) => {
    setBusyId(id)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(id)}/approve-payment`, {
        method: 'POST',
        body: JSON.stringify({ note: 'Cash payment approved' }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Approve failed')
    } finally {
      setBusyId('')
    }
  }

  const reject = async (id) => {
    setBusyId(id)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(id)}/reject-payment`, {
        method: 'POST',
        body: JSON.stringify({ note: 'Cash payment rejected' }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Reject failed')
    } finally {
      setBusyId('')
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Service orders — cash approval</h1>
          <p>Approve survey and interview orders after the customer marks cash payment.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load}>Refresh</button>
        </div>
      </div>

      {error ? <div className="note" style={{ borderColor: 'rgba(220,38,38,0.35)', marginBottom: 12 }}>{error}</div> : null}

      <div className="card">
        <div className="cardHead"><h3>Pending payment approval</h3></div>
        <div className="cardBody">
          {loading ? <div className="muted">Loading…</div> : null}
          {!loading && !orders.length ? <div className="muted">No orders waiting for approval.</div> : null}
          {!loading && orders.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Service</th>
                  <th>Contacts</th>
                  <th>Total</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.title}</td>
                    <td>{o.service_code}</td>
                    <td>{o.recipient_count}</td>
                    <td>{o.quote_total_gbp}</td>
                    <td>{o.payment_status}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button type="button" className="btn primary bsm" disabled={busyId === o.id} onClick={() => approve(o.id)}>Approve</button>
                      {' '}
                      <button type="button" className="btn soft bsm" disabled={busyId === o.id} onClick={() => reject(o.id)}>Reject</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </div>
    </>
  )
}
