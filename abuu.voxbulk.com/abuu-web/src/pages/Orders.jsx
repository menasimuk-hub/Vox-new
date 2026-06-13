import React, { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function shekel(agorot) {
  return `${(Number(agorot || 0) / 100).toFixed(2)} ₪`
}

export default function Orders() {
  const [rows, setRows] = useState([])
  const [me, setMe] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [profile, orders] = await Promise.all([
          apiFetch('/abuu/restaurant/me'),
          apiFetch('/abuu/restaurant/orders'),
        ])
        if (!cancelled) {
          setMe(profile)
          setRows(Array.isArray(orders) ? orders : [])
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className='card'>
      <h2>{me?.name_ar || me?.name_en || 'Orders'}</h2>
      {error ? <p className='error'>{error}</p> : null}
      {loading ? (
        <p className='muted'>Loading…</p>
      ) : (
        <table className='table'>
          <thead>
            <tr>
              <th>Time</th>
              <th>Status</th>
              <th>Payment</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.created_at ? new Date(row.created_at).toLocaleString('ar') : '—'}</td>
                <td>
                  <span className='pill'>{row.status}</span>
                </td>
                <td>{row.payment_status}</td>
                <td>{shekel(row.total_agorot)}</td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={4} className='muted'>
                  No orders yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      )}
    </div>
  )
}
