import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

function shekel(agorot) {
  return `${(Number(agorot || 0) / 100).toFixed(2)} ₪`
}

const TABS = [
  { key: 'assigned', label: 'ASSIGNED' },
  { key: 'on_route', label: 'ON ROUTE' },
  { key: 'delivered', label: 'DELIVERED' },
  { key: 'failed', label: 'FAILED' },
]

export default function Assignments() {
  const [rows, setRows] = useState([])
  const [me, setMe] = useState(null)
  const [tab, setTab] = useState('assigned')
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

  const filtered = useMemo(() => {
    const map = {
      assigned: (r) => r.status === 'assigned',
      on_route: (r) => r.status === 'on_route' || r.status === 'picked_up',
      delivered: (r) => r.status === 'delivered',
      failed: (r) => r.status === 'failed',
    }
    return rows.filter(map[tab] || (() => true))
  }, [rows, tab])

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
      <div className='tabs'>
        {TABS.map((t) => (
          <button key={t.key} type='button' className={tab === t.key ? 'btn primary' : 'btn'} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      {error ? <p className='error'>{error}</p> : null}
      {loading ? (
        <p className='muted'>Loading…</p>
      ) : (
        filtered.map((row) => {
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
              <p>
                <strong>Pickup:</strong> {row.pickup?.restaurant_name_ar || row.pickup?.restaurant_name_en} —{' '}
                {row.pickup?.address_text || '—'}
              </p>
              <p>
                <strong>Dropoff:</strong> {row.dropoff?.customer_name || row.dropoff?.customer_phone || 'Customer'} —{' '}
                {row.dropoff?.address_text || '—'}
              </p>
              <p className='muted'>Order status: {order.status || '—'}</p>
              <div className='actions'>
                {row.status === 'assigned' ? (
                  <button type='button' className='btn primary' disabled={busy === row.id} onClick={() => patchStatus(row.id, 'picked_up')}>
                    Picked up
                  </button>
                ) : null}
                {row.status === 'on_route' ? (
                  <button type='button' className='btn primary' disabled={busy === row.id} onClick={() => patchStatus(row.id, 'delivered')}>
                    Delivered
                  </button>
                ) : null}
              </div>
            </div>
          )
        })
      )}
      {!loading && !filtered.length ? <p className='muted'>No assignments in this tab.</p> : null}
    </>
  )
}
