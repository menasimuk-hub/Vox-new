import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../../lib/api'

const CURRENCIES = [
  { code: 'GBP', label: 'GB £' },
  { code: 'EUR', label: 'Euro €' },
  { code: 'CAD', label: 'CA $' },
  { code: 'AUD', label: 'AU $' },
  { code: 'USD', label: 'US $' },
]

export default function FeedbackPackagesPricing() {
  const [currency, setCurrency] = useState('GBP')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(() => new Set())

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/admin/customer-feedback/plans/pricing?currency=${encodeURIComponent(currency)}`)
      setItems(data?.items || [])
      setSelected(new Set())
    } catch (e) {
      setError(e?.message || 'Could not load plans')
    } finally {
      setLoading(false)
    }
  }, [currency])

  useEffect(() => {
    load()
  }, [load])

  const updateRow = (planId, field, value) => {
    setItems((rows) => rows.map((row) => (row.plan_id === planId ? { ...row, [field]: value } : row)))
  }

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/plans/pricing/bulk', {
        method: 'PUT',
        body: JSON.stringify({ currency, items }),
      })
      setMsg('All changes saved.')
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const freezeSelected = async () => {
    setItems((rows) => rows.map((row) => (selected.has(row.plan_id) ? { ...row, is_frozen: true } : row)))
    setMsg('Selected plans marked frozen locally — save to persist.')
  }

  return (
    <div className="pageWrap">
      <div className="pageHead">
        <div>
          <h1>Feedback customers — Plan pricing</h1>
          <p className="muted">Manage Customer Feedback plan tiers and pricing per currency. Renames persist after deploy (not reset on API restart).</p>
        </div>
        <Link className="btn soft bsm" to="/customer-feedback/subscriptions">Hub</Link>
      </div>

      {error ? <div className="alert error">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      <div className="card">
        <div className="runningSurveyTabs" style={{ padding: '0 12px' }}>
          {CURRENCIES.map((c) => (
            <button
              key={c.code}
              type="button"
              className={`runningSurveyTab${currency === c.code ? ' on' : ''}`}
              onClick={() => setCurrency(c.code)}
            >
              {c.label}
            </button>
          ))}
        </div>

        <div className="runningSurveyActionBar" style={{ padding: '12px 16px' }}>
          <button type="button" className="btn primary bsm" disabled={busy} onClick={save}>Save</button>
          <button type="button" className="btn soft bsm" disabled={!selected.size} onClick={freezeSelected}>Freeze</button>
          <button type="button" className="btn soft bsm" onClick={load}>Refresh</button>
        </div>

        <div className="tableWrap">
          <table className="table runningSurveyTable">
            <thead>
              <tr>
                <th />
                <th>Feedback plan name</th>
                <th>Price / mo ({currency})</th>
                <th>Price / yr ({currency})</th>
                <th>WA surveys / mo</th>
                <th>Web surveys / mo</th>
                <th>Locations</th>
                <th>Cost per promo msg</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="muted">Loading…</td></tr>
              ) : items.map((row) => (
                <tr key={row.plan_id} className={row.is_frozen ? 'muted' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      disabled={row.is_frozen}
                      checked={selected.has(row.plan_id)}
                      onChange={(e) => {
                        setSelected((prev) => {
                          const next = new Set(prev)
                          if (e.target.checked) next.add(row.plan_id)
                          else next.delete(row.plan_id)
                          return next
                        })
                      }}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      disabled={row.is_frozen}
                      value={row.name || ''}
                      onChange={(e) => updateRow(row.plan_id, 'name', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      disabled={row.is_frozen}
                      value={String((row.price_minor || 0) / 100)}
                      onChange={(e) => updateRow(row.plan_id, 'price_minor', Math.round(Number(e.target.value || 0) * 100))}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      disabled={row.is_frozen}
                      value={String((row.yearly_price_minor || row.price_minor * 10 || 0) / 100)}
                      onChange={(e) => updateRow(row.plan_id, 'yearly_price_minor', Math.round(Number(e.target.value || 0) * 100))}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      disabled={row.is_frozen}
                      value={row.wa_units_included ?? 0}
                      onChange={(e) => updateRow(row.plan_id, 'wa_units_included', Number(e.target.value || 0))}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      disabled={row.is_frozen}
                      value={row.web_units_included ?? 0}
                      placeholder="-1 = unlimited"
                      onChange={(e) => updateRow(row.plan_id, 'web_units_included', Number(e.target.value || 0))}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      disabled={row.is_frozen}
                      value={row.max_locations ?? 0}
                      onChange={(e) => updateRow(row.plan_id, 'max_locations', Number(e.target.value || 0))}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      disabled={row.is_frozen}
                      value={String((row.promo_message_cost_minor || 0) / 100)}
                      onChange={(e) => updateRow(row.plan_id, 'promo_message_cost_minor', Math.round(Number(e.target.value || 0) * 100))}
                    />
                  </td>
                </tr>
              ))}
              {!loading && !items.length ? <tr><td colSpan={6} className="muted">No plans for this currency.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
