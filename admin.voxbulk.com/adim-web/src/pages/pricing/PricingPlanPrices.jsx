import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import PricingPageFrame, { PricingLoadGate } from './PricingPageFrame'
import { penceToPounds, poundsToPence } from './pricingUtils'

import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'

function MoneyInput({ value, onChange, placeholder }) {
  return (
    <input
      className="input pricingInputSm pricingInputNum"
      type="number"
      step="0.01"
      min="0"
      value={value}
      placeholder={placeholder || '0.00'}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export default function PricingPlanPrices() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)
  // drafts[planId][currency] = { monthly, perMin, extraPerMin }
  const [drafts, setDrafts] = useState({})

  const load = useCallback(async () => {
    setError('')
    try {
      const body = await apiFetch('/admin/pricing/plan-prices')
      setData(body)
      const next = {}
      for (const plan of body.plans || []) {
        next[plan.plan_id] = {}
        for (const currency of body.supported_currencies || []) {
          const price = plan.prices?.[currency]
          next[plan.plan_id][currency] = {
            monthly: price?.monthly_price_minor != null ? penceToPounds(price.monthly_price_minor) : '',
            perMin: price ? penceToPounds(price.per_min_minor) : '',
            extraPerMin: price ? penceToPounds(price.extra_per_min_minor) : '',
          }
        }
      }
      setDrafts(next)
      return true
    } catch (e) {
      setError(e?.message || 'Could not load plan prices')
      return false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      await load()
      if (!cancelled) setLoading(false)
    })()
    return () => { cancelled = true }
  }, [load])

  const setDraft = (planId, currency, field, value) => {
    setDrafts((s) => ({
      ...s,
      [planId]: {
        ...(s[planId] || {}),
        [currency]: { ...((s[planId] || {})[currency] || {}), [field]: value },
      },
    }))
  }

  const saveAll = async () => {
    setSaving(true)
    setError('')
    setMsg('')
    try {
      for (const plan of data?.plans || []) {
        for (const currency of data?.supported_currencies || []) {
          const draft = drafts?.[plan.plan_id]?.[currency]
          if (!draft) continue
          const payload = {
            monthly_price_minor: draft.monthly === '' ? null : poundsToPence(draft.monthly),
            per_min_minor: poundsToPence(draft.perMin),
            extra_per_min_minor: poundsToPence(draft.extraPerMin),
          }
          await apiFetch(`/admin/pricing/plan-prices/${encodeURIComponent(plan.plan_id)}/${currency}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
          })
        }
      }
      await load()
      setMsg('All plan prices saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <PricingLoadGate
      loading={loading}
      error={!data ? error : ''}
      title="Plan prices"
      description="Explicit price per currency — no FX conversion."
      onRetry={load}
    >
      {data ? (
        <PricingPageFrame
          title="Plan prices"
          description="Set the exact monthly price and per-minute rates for each currency. Customers are billed in their org currency."
          error={error}
          msg={msg}
          actions={
            <button className="btn primary" type="button" disabled={saving} onClick={() => void saveAll()}>
              {saving ? 'Saving…' : 'Save all prices'}
            </button>
          }
        >
          <div className="pricingPlanPricesStack">
            {(data.plans || []).map((plan) => (
              <div key={plan.plan_id} className="pricingPlanPriceCard">
                <div className="pricingPlanPriceHead">
                  <strong>{plan.plan_name}</strong>
                  <span className="muted">{plan.plan_code}</span>
                  {plan.is_enterprise ? <span className="pill p-cyan">Enterprise — custom pricing</span> : null}
                  {!plan.is_active ? <span className="pill p-amber">Inactive</span> : null}
                </div>
                {plan.is_enterprise ? (
                  <p className="muted">Enterprise pricing is agreed per customer (Custom org tab).</p>
                ) : (
                  <table className="pricingPlanPriceTable">
                    <thead>
                      <tr>
                        <th>Currency</th>
                        <th>Monthly price</th>
                        <th>Per minute</th>
                        <th>Extra per minute</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.supported_currencies || []).map((currency) => {
                        const draft = drafts?.[plan.plan_id]?.[currency] || {}
                        const symbol = CURRENCY_SYMBOLS[currency] || currency
                        return (
                          <tr key={currency}>
                            <td><strong>{symbol} {currency}</strong></td>
                            <td><MoneyInput value={draft.monthly ?? ''} onChange={(v) => setDraft(plan.plan_id, currency, 'monthly', v)} placeholder="Leave blank for PAYG" /></td>
                            <td><MoneyInput value={draft.perMin ?? ''} onChange={(v) => setDraft(plan.plan_id, currency, 'perMin', v)} /></td>
                            <td><MoneyInput value={draft.extraPerMin ?? ''} onChange={(v) => setDraft(plan.plan_id, currency, 'extraPerMin', v)} /></td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        </PricingPageFrame>
      ) : null}
    </PricingLoadGate>
  )
}
