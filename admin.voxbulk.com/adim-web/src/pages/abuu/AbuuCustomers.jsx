import React, { useEffect, useState } from 'react'
import { fetchAbuuCustomers, fetchAbuuCustomerHistory } from '../../lib/abuuApi'
import { dateText, shekel } from '../../lib/abuuAdminUtils'

export default function AbuuCustomers() {
  const [rows, setRows] = useState([])
  const [selected, setSelected] = useState(null)
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const data = await fetchAbuuCustomers({ limit: 100 })
        if (!cancelled) setRows(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const openHistory = async (customer) => {
    setSelected(customer)
    setHistory(null)
    setError('')
    try {
      const data = await fetchAbuuCustomerHistory(customer.id)
      setHistory(data)
    } catch (e) {
      setError(e?.message || 'History load failed')
    }
  }

  return (
    <div className='card'>
      <div className='cardBody'>
        {error ? <p className='formError'>{error}</p> : null}
        {loading ? (
          <p className='muted'>Loading customers…</p>
        ) : (
          <div className='tableWrap'>
            <table className='table'>
              <thead>
                <tr>
                  <th>Phone</th>
                  <th>Name</th>
                  <th>Language</th>
                  <th>Orders</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.phone}</td>
                    <td>{row.name || '—'}</td>
                    <td>{row.preferred_language}</td>
                    <td>{row.order_count}</td>
                    <td>
                      <button type='button' className='btn sm' onClick={() => openHistory(row)}>
                        History
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {selected && history ? (
          <div className='card nested' style={{ marginTop: 24 }}>
            <div className='cardBody'>
              <h3 className='h3'>
                {selected.phone} — {history.customer?.order_count || 0} orders
              </h3>
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Status</th>
                      <th>Payment</th>
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(history.orders || []).map((order) => (
                      <tr key={order.id}>
                        <td>{dateText(order.created_at)}</td>
                        <td>{order.status}</td>
                        <td>{order.payment_status}</td>
                        <td>{shekel(order.total_agorot)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
