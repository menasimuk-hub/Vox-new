import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  cancelAbuuPaidOrder,
  fetchAbuuOrder,
  fetchAbuuOrders,
  markAbuuOrderPaid,
  markAbuuRefundProcessed,
  recoverAbuuOrder,
} from '../../lib/abuuApi'
import { abuuStatusClass, dateText, shekel } from '../../lib/abuuAdminUtils'

const STATUS_OPTIONS = [
  '',
  'draft',
  'confirmed',
  'paid',
  'sent_to_restaurant',
  'preparing',
  'ready',
  'assigned_to_driver',
  'picked_up',
  'delivered',
  'cancelled',
]

export default function AbuuOrders() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [statusFilter, setStatusFilter] = useState('confirmed')
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState(null)

  const load = useCallback(async () => {
    setError('')
    const orders = await fetchAbuuOrders({ status: statusFilter || undefined, limit: 200 })
    setRows(Array.isArray(orders) ? orders : [])
  }, [statusFilter])

  const loadDetail = useCallback(async (orderId) => {
    if (!orderId) {
      setDetail(null)
      return
    }
    const data = await fetchAbuuOrder(orderId)
    setDetail(data)
  }, [])

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

  useEffect(() => {
    loadDetail(selectedId).catch((e) => setError(e.message))
  }, [selectedId, loadDetail])

  const stats = useMemo(() => {
    const pending = rows.filter((r) => String(r.payment_status || '').includes('pending'))
    return { total: rows.length, pending: pending.length }
  }, [rows])

  const onMarkPaid = async (row) => {
    if (!row?.id) return
    setBusy(row.id)
    try {
      await markAbuuOrderPaid(row.id)
      await load()
      if (selectedId === row.id) await loadDetail(row.id)
    } catch (e) {
      setError(e?.message || 'Mark paid failed')
    } finally {
      setBusy('')
    }
  }

  const onCancelPaid = async () => {
    if (!detail?.id) return
    setBusy('cancel')
    try {
      await cancelAbuuPaidOrder(detail.id, 'Admin cancel')
      await load()
      await loadDetail(detail.id)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  const onRefundProcessed = async () => {
    if (!detail?.id) return
    setBusy('refund')
    try {
      await markAbuuRefundProcessed(detail.id)
      await loadDetail(detail.id)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  const onRecover = async (action) => {
    if (!detail?.id) return
    setBusy(action)
    try {
      await recoverAbuuOrder(detail.id, { action })
      await load()
      await loadDetail(detail.id)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='card'>
      <div className='cardBody'>
        <div className='billingPageToolbar'>
          <div className='billingStats'>
            <span className='pill'>{stats.total} orders</span>
            <span className='pill warn'>{stats.pending} pending payment</span>
          </div>
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
          <p className='muted'>Loading orders…</p>
        ) : (
          <div className='tableWrap'>
            <table className='table billingTable'>
              <thead>
                <tr>
                  <th>Created</th>
                  <th>Order</th>
                  <th>Status</th>
                  <th>Payment</th>
                  <th>Total</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className={selectedId === row.id ? 'selected' : ''}>
                    <td>{dateText(row.created_at)}</td>
                    <td>
                      <button type='button' className='btn link sm' onClick={() => setSelectedId(row.id)}>
                        <code>{row.id.slice(0, 8)}</code>
                      </button>
                      <div className='muted small'>{row.restaurant_id?.slice(0, 8)}</div>
                    </td>
                    <td>
                      <span className={abuuStatusClass(row.status)}>{row.status}</span>
                    </td>
                    <td>
                      <span className={abuuStatusClass(row.payment_status)}>{row.payment_status}</span>
                    </td>
                    <td>{shekel(row.total_agorot)}</td>
                    <td className='tableActions'>
                      {row.status === 'confirmed' ? (
                        <button
                          type='button'
                          className='btn primary sm'
                          disabled={busy === row.id}
                          onClick={() => onMarkPaid(row)}
                        >
                          Mark paid
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {!rows.length ? (
                  <tr>
                    <td colSpan={6} className='muted'>
                      No orders for this filter.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
        {detail ? (
          <div className='card' style={{ marginTop: 16 }}>
            <div className='cardBody'>
              <h3>Order {detail.id.slice(0, 8)}</h3>
              <p>
                Status: <span className={abuuStatusClass(detail.status)}>{detail.status}</span>
                {detail.refund_ready ? <span className='pill warn'> Refund ready</span> : null}
                {detail.location_missing ? <span className='pill warn'> Location missing</span> : null}
              </p>
              {detail.prep_delay_note ? <p className='muted'>Prep delay: {detail.prep_delay_note}</p> : null}
              {detail.delivery_address ? (
                <p className='muted small'>Delivery: {detail.delivery_address.address_text}</p>
              ) : null}
              <div className='billingPageToolbar'>
                {['sent_to_restaurant', 'preparing'].includes(detail.status) ? (
                  <button type='button' className='btn sm' disabled={busy === 'cancel'} onClick={onCancelPaid}>
                    Cancel paid
                  </button>
                ) : null}
                {detail.refund_ready ? (
                  <button type='button' className='btn sm' disabled={busy === 'refund'} onClick={onRefundProcessed}>
                    Mark refund processed
                  </button>
                ) : null}
                {detail.location_missing ? (
                  <button type='button' className='btn sm' disabled={busy === 'clear_location_missing'} onClick={() => onRecover('clear_location_missing')}>
                    Clear location flag
                  </button>
                ) : null}
                {['ready', 'assigned_to_driver'].includes(detail.status) ? (
                  <button type='button' className='btn sm' disabled={busy === 'reassign_driver'} onClick={() => onRecover('reassign_driver')}>
                    Reassign driver
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
