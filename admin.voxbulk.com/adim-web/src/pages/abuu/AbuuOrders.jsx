import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  assignAbuuDriver,
  fetchAbuuDrivers,
  fetchAbuuOrders,
  markAbuuOrderPaid,
} from '../../lib/abuuApi'
import { abuuStatusClass, dateText, shekel } from '../../lib/abuuAdminUtils'

const STATUS_OPTIONS = ['', 'draft', 'pending_payment', 'preparing', 'out_for_delivery', 'delivered', 'cancelled']

export default function AbuuOrders() {
  const [rows, setRows] = useState([])
  const [drivers, setDrivers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending_payment')
  const [assignDriverId, setAssignDriverId] = useState({})

  const load = useCallback(async () => {
    setError('')
    const [orders, driverRows] = await Promise.all([
      fetchAbuuOrders({ status: statusFilter || undefined, limit: 200 }),
      fetchAbuuDrivers({ limit: 100 }),
    ])
    setRows(Array.isArray(orders) ? orders : [])
    setDrivers(Array.isArray(driverRows) ? driverRows : [])
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
    } catch (e) {
      setError(e?.message || 'Mark paid failed')
    } finally {
      setBusy('')
    }
  }

  const onAssign = async (row) => {
    const driverId = assignDriverId[row.id]
    if (!row?.id || !driverId) return
    setBusy(`assign-${row.id}`)
    try {
      await assignAbuuDriver(row.id, driverId)
      await load()
    } catch (e) {
      setError(e?.message || 'Assign failed')
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
                  <tr key={row.id}>
                    <td>{dateText(row.created_at)}</td>
                    <td>
                      <code>{row.id.slice(0, 8)}</code>
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
                      {row.status === 'pending_payment' ? (
                        <button
                          type='button'
                          className='btn primary sm'
                          disabled={busy === row.id}
                          onClick={() => onMarkPaid(row)}
                        >
                          Mark paid
                        </button>
                      ) : null}
                      {row.status === 'preparing' ? (
                        <div className='inlineAssign'>
                          <select
                            value={assignDriverId[row.id] || ''}
                            onChange={(e) =>
                              setAssignDriverId((prev) => ({ ...prev, [row.id]: e.target.value }))
                            }
                          >
                            <option value=''>Assign driver…</option>
                            {drivers
                              .filter((d) => d.is_available)
                              .map((d) => (
                                <option key={d.id} value={d.id}>
                                  {d.name}
                                </option>
                              ))}
                          </select>
                          <button
                            type='button'
                            className='btn sm'
                            disabled={busy === `assign-${row.id}` || !assignDriverId[row.id]}
                            onClick={() => onAssign(row)}
                          >
                            Assign
                          </button>
                        </div>
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
      </div>
    </div>
  )
}
