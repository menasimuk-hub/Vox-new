import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Globe, Info, Infinity, PackageOpen, Plus, Save, Trash2 } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'
import { penceToPounds, poundsToPence } from '../pricing/pricingUtils'
import './feedbackPackagesTheme.css'

const CURRENCIES = [
  { code: 'GBP', label: 'GB £', zone: 'gb' },
  { code: 'EUR', label: 'Euro €', zone: 'eu' },
  { code: 'USD', label: 'US $', zone: 'us' },
  { code: 'CAD', label: 'CA $', zone: 'ca' },
  { code: 'AUD', label: 'AU $', zone: 'au' },
]

const SEEDED_CODES = new Set(['cf_starter_gb', 'cf_growth_gb', 'cf_pro_gb', 'cf_business_gb'])

function webUnitsUnlimited(webUnits) {
  return Number(webUnits) < 0
}

export default function FeedbackPackagesPricing() {
  const [currency, setCurrency] = useState('GBP')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [items, setItems] = useState([])
  const [yearlyManual, setYearlyManual] = useState(() => new Set())
  const [manageMode, setManageMode] = useState(false)
  const [toast, setToast] = useState({ show: false, message: '', error: false })
  const toastTimer = useRef(null)

  const showToast = useCallback((message, isError = false) => {
    setToast({ show: true, message, error: isError })
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => {
      setToast((t) => ({ ...t, show: false }))
    }, 3000)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/admin/customer-feedback/plans/pricing?currency=${encodeURIComponent(currency)}`)
      setItems(data?.items || [])
      setYearlyManual(new Set())
    } catch (e) {
      setError(e?.message || 'Could not load plans')
    } finally {
      setLoading(false)
    }
  }, [currency])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => () => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
  }, [])

  const updateRow = (planId, field, value) => {
    setItems((rows) => rows.map((row) => (row.plan_id === planId ? { ...row, [field]: value } : row)))
  }

  const updateMonthly = (planId, poundsStr) => {
    const priceMinor = poundsToPence(poundsStr)
    setItems((rows) =>
      rows.map((row) => {
        if (row.plan_id !== planId) return row
        const next = { ...row, price_minor: priceMinor }
        if (!yearlyManual.has(planId) && priceMinor > 0) {
          next.yearly_price_minor = priceMinor * 10
        }
        return next
      }),
    )
  }

  const updateYearly = (planId, poundsStr) => {
    setYearlyManual((prev) => new Set(prev).add(planId))
    updateRow(planId, 'yearly_price_minor', poundsToPence(poundsStr))
  }

  const toggleWebUnlimited = (planId, unlimited) => {
    updateRow(planId, 'web_units_included', unlimited ? -1 : 200)
  }

  const save = async (subset) => {
    setBusy(true)
    setError('')
    try {
      const payload = subset || items
      await apiFetch('/admin/customer-feedback/plans/pricing/bulk', {
        method: 'PUT',
        body: JSON.stringify({ currency, items: payload }),
      })
      showToast('All packages saved. Changes apply to new subscriptions and renewals.')
      await load()
    } catch (e) {
      const msg = e?.message || 'Save failed'
      setError(msg)
      showToast(msg, true)
    } finally {
      setBusy(false)
    }
  }

  const saveOne = async (planId) => {
    const row = items.find((r) => r.plan_id === planId)
    if (!row) return
    await save([row])
    showToast('Package saved successfully!')
  }

  const addPackage = async () => {
    setBusy(true)
    setError('')
    try {
      const zone = CURRENCIES.find((c) => c.code === currency)?.zone || 'gb'
      const data = await apiFetch('/admin/customer-feedback/plans/pricing', {
        method: 'POST',
        body: JSON.stringify({ currency, market_zone: zone, name: 'Enterprise' }),
      })
      if (data?.item) {
        setItems((prev) => [...prev, data.item])
        showToast('New Enterprise package created!')
      } else {
        await load()
        showToast('New package created!')
      }
    } catch (e) {
      const msg = e?.message || 'Could not create package'
      setError(msg)
      showToast(msg, true)
    } finally {
      setBusy(false)
    }
  }

  const deletePackage = async (planId) => {
    if (!window.confirm('Are you sure you want to delete this package?')) return
    setBusy(true)
    setError('')
    try {
      await apiFetch(`/admin/customer-feedback/plans/pricing/${encodeURIComponent(planId)}`, {
        method: 'DELETE',
      })
      setItems((prev) => prev.filter((r) => r.plan_id !== planId))
      showToast('Package deleted successfully!')
    } catch (e) {
      const msg = e?.message || 'Delete failed'
      setError(msg)
      showToast(msg, true)
    } finally {
      setBusy(false)
    }
  }

  const symbol = CURRENCY_SYMBOLS[currency] || currency
  const codeEditable = (code) => !SEEDED_CODES.has(String(code || '').toLowerCase())

  return (
    <div className="cfpTheme">
      <div className="cfp-app">
        <div className="page-header">
          <h1>Customer feedback pricing</h1>
          <p>
            Manage Starter, Growth, and Business tiers — locations, survey allowances, and monthly/yearly prices per
            currency.
          </p>
          <Link className="hub-badge" to="/customer-feedback/subscriptions">
            <Globe size={12} /> Feedback hub
          </Link>
        </div>

        <div className="top-bar">
          <div className="currency-tabs">
            {CURRENCIES.map((c) => (
              <button
                key={c.code}
                type="button"
                className={`currency-tab${currency === c.code ? ' active' : ''}`}
                onClick={() => setCurrency(c.code)}
              >
                {c.label}
              </button>
            ))}
          </div>
          <div className="top-actions">
            <button
              type="button"
              className={`cfp-btn cfp-btn-ghost cfp-btn-sm${manageMode ? ' cfp-btn-primary' : ''}`}
              onClick={() => setManageMode((v) => !v)}
            >
              {manageMode ? 'Done' : 'Manage'}
            </button>
            <button type="button" className="cfp-btn cfp-btn-primary" disabled={busy || loading} onClick={() => void addPackage()}>
              <Plus size={14} /> Create package
            </button>
            <button type="button" className="cfp-btn cfp-btn-success" disabled={busy || loading} onClick={() => void save()}>
              <Save size={14} /> {busy ? 'Saving…' : 'Save all'}
            </button>
          </div>
        </div>

        <div className="vat-note">
          <Info size={14} style={{ flexShrink: 0, marginTop: 1, color: '#1a2332' }} />
          <span>
            Prices are ex-VAT. VAT is applied at checkout based on the customer&apos;s country — manage rates in{' '}
            <Link to="/billing/tax">Billing → Tax &amp; VAT</Link>.
          </span>
        </div>

        {error ? (
          <p className="vat-note" style={{ background: '#f8e8e4', borderColor: '#d4b0a8', color: '#8a4a3a' }}>
            {error}
          </p>
        ) : null}

        {loading ? (
          <div className="cfp-loading">Loading packages…</div>
        ) : !items.length ? (
          <div className="empty-state">
            <PackageOpen size={32} style={{ margin: '0 auto 10px', display: 'block' }} />
            <p>No packages yet. Click &quot;Create package&quot; to add one.</p>
          </div>
        ) : (
          <div id="packageContainer">
            {items.map((row) => {
              const frozen = Boolean(row.is_frozen)
              const unlimitedWeb = webUnitsUnlimited(row.web_units_included)
              const canEditCode = codeEditable(row.code)
              return (
                <div key={row.plan_id} className="package-row">
                  <div className="row-header">
                    <div className="left">
                      <input
                        className="name-input"
                        type="text"
                        disabled={frozen}
                        value={row.name || ''}
                        onChange={(e) => updateRow(row.plan_id, 'name', e.target.value)}
                        placeholder="Package name"
                      />
                      <input
                        className="code-input"
                        type="text"
                        readOnly={!canEditCode || frozen}
                        value={row.code || ''}
                        onChange={(e) => updateRow(row.plan_id, 'code', e.target.value)}
                        placeholder="Package code"
                      />
                      {frozen ? <span className="status-pill">Frozen</span> : null}
                      {!row.is_active ? <span className="status-pill">Inactive</span> : null}
                    </div>
                    <div className="right">
                      {manageMode && !frozen ? (
                        <button
                          type="button"
                          className="cfp-btn cfp-btn-danger cfp-btn-sm"
                          disabled={busy}
                          onClick={() => void deletePackage(row.plan_id)}
                        >
                          <Trash2 size={12} />
                        </button>
                      ) : null}
                    </div>
                  </div>

                  <div className="row-body">
                    <table>
                      <thead>
                        <tr>
                          <th style={{ width: 80 }}>Locations</th>
                          <th style={{ width: 100 }}>WhatsApp / mo</th>
                          <th style={{ width: 120 }}>Web surveys / mo</th>
                          <th style={{ width: 90 }}>Monthly ({symbol})</th>
                          <th style={{ width: 90 }}>Yearly ({symbol})</th>
                          <th style={{ width: 90 }}>Promo msg</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>
                            <input
                              type="number"
                              min="0"
                              disabled={frozen}
                              value={row.max_locations ?? 0}
                              onChange={(e) => updateRow(row.plan_id, 'max_locations', Number(e.target.value || 0))}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              min="0"
                              disabled={frozen}
                              value={row.wa_units_included ?? 0}
                              onChange={(e) => updateRow(row.plan_id, 'wa_units_included', Number(e.target.value || 0))}
                            />
                          </td>
                          <td>
                            {unlimitedWeb ? (
                              <span className="web-unlimited-badge">
                                <Infinity size={12} /> Unlimited
                              </span>
                            ) : (
                              <input
                                type="number"
                                min="0"
                                disabled={frozen}
                                value={row.web_units_included ?? 0}
                                onChange={(e) =>
                                  updateRow(row.plan_id, 'web_units_included', Number(e.target.value || 0))
                                }
                              />
                            )}
                            <div className="unlimited-toggle">
                              <label className="toggle-switch">
                                <input
                                  type="checkbox"
                                  disabled={frozen}
                                  checked={unlimitedWeb}
                                  onChange={(e) => toggleWebUnlimited(row.plan_id, e.target.checked)}
                                />
                                <span className="toggle-slider" />
                              </label>
                              <label>Unlimited</label>
                            </div>
                          </td>
                          <td>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              disabled={frozen}
                              value={penceToPounds(row.price_minor || 0)}
                              onChange={(e) => updateMonthly(row.plan_id, e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              disabled={frozen}
                              value={penceToPounds(row.yearly_price_minor || (row.price_minor || 0) * 10)}
                              onChange={(e) => updateYearly(row.plan_id, e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              disabled={frozen}
                              value={penceToPounds(row.promo_message_cost_minor || 0)}
                              onChange={(e) =>
                                updateRow(row.plan_id, 'promo_message_cost_minor', poundsToPence(e.target.value))
                              }
                            />
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <div className="row-footer">
                    <div>
                      <span className="badge">Yearly billing</span>
                      <span className="free-text">
                        <span>2 months free (×10)</span>
                      </span>
                    </div>
                    <div className="footer-actions">
                      <button
                        type="button"
                        className="cfp-btn cfp-btn-sm"
                        disabled={busy || frozen}
                        onClick={() => void saveOne(row.plan_id)}
                      >
                        <Save size={12} /> Save
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className={`cfp-toast${toast.show ? ' show' : ''}${toast.error ? ' error' : ''}`} role="status">
        {toast.message}
      </div>
    </div>
  )
}
