import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function shekel(agorot) {
  return `${(Number(agorot || 0) / 100).toFixed(2)} ₪`
}

export default function Assignments() {
  const [rows, setRows] = useState([])
  const [me, setMe] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    const [profile, assignments] = await Promise.all([
      apiFetch('/abuu/driver/me'),
      apiFetch('/abuu/driver/assignments'),
    ])
    setMe(profile)
    setRows(Array.isArray(assignments) ? assignments : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const patchStatus = async (assignmentId, status) => {
    setBusy(assignmentId)
    setError('')
    try {
      await apiFetch(`/abuu/driver/assignments/${assignmentId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      })
      await load()
    } catch (e) {
      setError(e.message || 'Update failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <h2>{me?.name ? `Hello, ${me.name}` : 'Deliveries'}</h2>
      {error ? <p className='error'>{error}</p> : null}
      {loading ? (
        <p className='muted'>Loading…</p>
      ) : (
        rows.map((row) => {
          const order = row.order || {}
          return (
            <div key={row.id} className='card'>
              <div>
                <span className='pill'>{row.status}</span>
                <span className='muted' style={{ marginLeft: 8 }}>
                  Order {String(order.id || row.order_id || '').slice(0, 8)}
                </span>
              </div>
              <p>
                Total: <strong>{shekel(order.total_agorot)}</strong>
              </p>
              <p className='muted'>Order status: {order.status || '—'}</p>
              <div className='actions'>
                {row.status === 'assigned' ? (
                  <button
                    type='button'
                    className='btn primary'
                    disabled={busy === row.id}
                    onClick={() => patchStatus(row.id, 'picked_up')}
                  >
                    Picked up
                  </button>
                ) : null}
                {row.status === 'picked_up' ? (
                  <button
                    type='button'
                    className='btn primary'
                    disabled={busy === row.id}
                    onClick={() => patchStatus(row.id, 'delivered')}
                  >
                    Delivered
                  </button>
                ) : null}
              </div>
            </div>
          )
        })
      )}
      {!loading && !rows.length ? <p className='muted'>No assignments yet.</p> : null}
    </>
  )
}
