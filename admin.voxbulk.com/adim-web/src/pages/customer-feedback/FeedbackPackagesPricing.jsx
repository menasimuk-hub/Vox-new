import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'
import PricingPageFrame, { PricingLoadGate } from '../pricing/PricingPageFrame'
import { penceToPounds, poundsToPence } from '../pricing/pricingUtils'

const CURRENCIES = [
  { code: 'GBP', label: 'GB £' },
  { code: 'EUR', label: 'Euro €' },
  { code: 'USD', label: 'US $' },
  { code: 'CAD', label: 'CA $' },
  { code: 'AUD', label: 'AU $' },
]

function MoneyInput({ value, onChange, disabled, placeholder }) {
  return (
    <input
      className="input pricingInputSm pricingInputNum"
      type="number"
      step="0.01"
      min="0"
      value={value}
      disabled={disabled}
      placeholder={placeholder || '0.00'}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function NumInput({ value, onChange, disabled, placeholder }) {
  return (
    <input
      className="input pricingInputSm pricingInputNum"
      type="number"
      min="0"
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function webUnitsUnlimited(webUnits) {
  return Number(webUnits) < 0
}

export default function FeedbackPackagesPricing() {
  const [currency, setCurrency] = useState('GBP')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [items, setItems] = useState([])
  const [yearlyManual, setYearlyManual] = useState(() => new Set())

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

  const save = async () => {
    setBusy(true)
    setError('')
    setMsg('')
    try {
      await apiFetch('/admin/customer-feedback/plans/pricing/bulk', {
        method: 'PUT',
        body: JSON.stringify({ currency, items }),
      })
      setMsg('All Customer feedback pricing saved. Changes apply to new subscriptions and renewals.')
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const symbol = CURRENCY_SYMBOLS[currency] || currency

  return (
    <div className="pageWrap">
      <div className="pageHead">
        <div>
          <h1>Customer feedback pricing</h1>
          <p className="muted">
            Manage Starter, Growth, and Business tiers — locations, survey allowances, and monthly/yearly prices per currency.
          </p>
        </div>
        <Link className="btn soft bsm" to="/customer-feedback/subscriptions">
          Feedback hub
        </Link>
      </div>

      <PricingLoadGate
        loading={loading}
        error={!items.length && error ? error : ''}
        title="Customer feedback pricing"
        description="Starter, Growth, and Business packages for WhatsApp and web QR surveys."
        onRetry={load}
      >
        <PricingPageFrame
          title={`Packages — ${currency}`}
          description="Prices are ex-VAT. Yearly billing = 10 months (2 months free). Edits flow to the customer dashboard package picker."
          error={error}
          msg={msg}
          actions={
            <button type="button" className="btn primary" disabled={busy || loading} onClick={() => void save()}>
              {busy ? 'Saving…' : 'Save all'}
            </button>
          }
        >
          <div className="runningSurveyTabs" style={{ marginBottom: 16 }}>
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

          <p className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
            Prices are ex-VAT. VAT is applied at checkout based on the customer&apos;s country — manage rates in{' '}
            <Link to="/billing/tax">Billing → Tax &amp; VAT</Link>.
          </p>

          {!loading && !items.length ? (
            <p className="muted">No plans for {currency}. Check that feedback packages are seeded for this market zone.</p>
          ) : (
            <div className="pricingPlanPricesStack">
              {items.map((row) => {
                const frozen = Boolean(row.is_frozen)
                const unlimitedWeb = webUnitsUnlimited(row.web_units_included)
                return (
                  <div key={row.plan_id} className="pricingPlanPriceCard">
                    <div className="pricingPlanPriceHead">
                      <input
                        className="input"
                        disabled={frozen}
                        value={row.name || ''}
                        onChange={(e) => updateRow(row.plan_id, 'name', e.target.value)}
                        style={{ fontWeight: 600, maxWidth: 220 }}
                      />
                      <span className="muted">{row.code}</span>
                      {frozen ? <span className="pill p-amber">Frozen</span> : null}
                      {!row.is_active ? <span className="pill p-amber">Inactive</span> : null}
                    </div>

                    <table className="pricingPlanPriceTable">
                      <thead>
                        <tr>
                          <th>Locations</th>
                          <th>WhatsApp surveys / mo</th>
                          <th>Web surveys / mo</th>
                          <th>Monthly ({symbol})</th>
                          <th>Yearly ({symbol})</th>
                          <th>Promo msg cost</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>
                            <NumInput
                              disabled={frozen}
                              value={row.max_locations ?? 0}
                              onChange={(v) => updateRow(row.plan_id, 'max_locations', Number(v || 0))}
                            />
                          </td>
                          <td>
                            <NumInput
                              disabled={frozen}
                              value={row.wa_units_included ?? 0}
                              onChange={(v) => updateRow(row.plan_id, 'wa_units_included', Number(v || 0))}
                            />
                          </td>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                                <input
                                  type="checkbox"
                                  disabled={frozen}
                                  checked={unlimitedWeb}
                                  onChange={(e) => toggleWebUnlimited(row.plan_id, e.target.checked)}
                                />
                                Unlimited
                              </label>
                              {!unlimitedWeb ? (
                                <NumInput
                                  disabled={frozen}
                                  value={row.web_units_included ?? 0}
                                  onChange={(v) => updateRow(row.plan_id, 'web_units_included', Number(v || 0))}
                                />
                              ) : (
                                <span className="pill p-cyan">Unlimited</span>
                              )}
                            </div>
                          </td>
                          <td>
                            <MoneyInput
                              disabled={frozen}
                              value={penceToPounds(row.price_minor || 0)}
                              onChange={(v) => updateMonthly(row.plan_id, v)}
                            />
                          </td>
                          <td>
                            <MoneyInput
                              disabled={frozen}
                              value={penceToPounds(row.yearly_price_minor || (row.price_minor || 0) * 10)}
                              onChange={(v) => updateYearly(row.plan_id, v)}
                            />
                            <span className="muted" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                              2 months free (×10)
                            </span>
                          </td>
                          <td>
                            <MoneyInput
                              disabled={frozen}
                              value={penceToPounds(row.promo_message_cost_minor || 0)}
                              onChange={(v) => updateRow(row.plan_id, 'promo_message_cost_minor', poundsToPence(v))}
                            />
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )
              })}
            </div>
          )}
        </PricingPageFrame>
      </PricingLoadGate>
    </div>
  )
}
