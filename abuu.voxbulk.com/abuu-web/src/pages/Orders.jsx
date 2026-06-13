import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

function shekel(agorot) {
  return `${(Number(agorot || 0) / 100).toFixed(2)} ₪`
}

const BOARDS = [
  { key: 'new', label: 'NEW', statuses: ['sent_to_restaurant'] },
  { key: 'preparing', label: 'PREPARING', statuses: ['preparing'] },
  { key: 'ready', label: 'READY', statuses: ['ready'] },
  { key: 'cancelled', label: 'CANCELLED', statuses: ['cancelled'] },
  { key: 'completed', label: 'COMPLETED', statuses: ['delivered'] },
]

export default function Orders() {
  const [rows, setRows] = useState([])
  const [me, setMe] = useState(null)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    const [profile, orders] = await Promise.all([
      apiFetch('/abuu/restaurant/me'),
      apiFetch('/abuu/restaurant/orders'),
    ])
    setMe(profile)
    setRows(Array.isArray(orders) ? orders : [])
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

  const grouped = useMemo(() => {
    const map = Object.fromEntries(BOARDS.map((b) => [b.key, []]))
    for (const row of rows) {
      const board = BOARDS.find((b) => b.statuses.includes(row.status))
      if (board) map[board.key].push(row)
    }
    return map
  }, [rows])

  const openDetail = async (orderId) => {
    setSelected(orderId)
    setDetail(null)
    try {
      const data = await apiFetch(`/abuu/restaurant/orders/${orderId}`)
      setDetail(data)
    } catch (e) {
      setError(e.message || 'Detail failed')
    }
  }

  const action = async (orderId, path) => {
    setBusy(orderId)
    setError('')
    try {
      await apiFetch(`/abuu/restaurant/orders/${orderId}/${path}`, { method: 'POST', body: '{}' })
      await load()
      if (selected === orderId) await openDetail(orderId)
    } catch (e) {
      setError(e.message || 'Action failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='card'>
      <h2>{me?.name_ar || me?.name_en || 'Task board'}</h2>
      {error ? <p className='error'>{error}</p> : null}
      {loading ? (
        <p className='muted'>Loading…</p>
      ) : (
        <div className='board'>
          {BOARDS.map((board) => (
            <div key={board.key} className='boardCol'>
              <h3>
                {board.label} ({grouped[board.key].length})
              </h3>
              {grouped[board.key].map((row) => (
                <div key={row.id} className='boardCard' onClick={() => openDetail(row.id)}>
                  <div className='pill'>{row.status}</div>
                  <div>{shekel(row.total_agorot)}</div>
                  <div className='muted small'>{row.created_at ? new Date(row.created_at).toLocaleString('ar') : '—'}</div>
                  {board.key === 'new' ? (
                    <button type='button' className='btn sm' disabled={busy === row.id} onClick={(e) => { e.stopPropagation(); action(row.id, 'preparing') }}>
                      Start preparing
                    </button>
                  ) : null}
                  {board.key === 'preparing' ? (
                    <button type='button' className='btn primary sm' disabled={busy === row.id} onClick={(e) => { e.stopPropagation(); action(row.id, 'ready') }}>
                      Mark ready
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {detail ? (
        <div className='card detail'>
          <h3>Order {String(detail.id || '').slice(0, 8)}</h3>
          <p>Notes: {detail.notes || '—'}</p>
          <p>
            Customer: {detail.customer?.name || detail.customer?.phone || '—'}
          </p>
          <p>Address: {detail.delivery_address?.address_text || '—'}</p>
          <ul>
            {(detail.items || []).map((item) => (
              <li key={item.id}>
                {item.name_ar || item.name_en} × {item.quantity} — {shekel(item.line_total_agorot)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
