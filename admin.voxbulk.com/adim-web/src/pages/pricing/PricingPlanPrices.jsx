import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import PricingPageFrame, { PricingLoadGate } from './PricingPageFrame'
import { penceToPounds, poundsToPence } from './pricingUtils'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'

function MoneyInput({ value, onChange, placeholder }) {
  return (
    <Input
      className="h-8"
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
  // drafts[planId][currency] = { monthly, perMin, extraPerMin, _edited }
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
            manual_override: Boolean(price?.manual_override),
            _edited: false,
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
        [currency]: {
          ...((s[planId] || {})[currency] || {}),
          [field]: value,
          ...(currency !== 'GBP' ? { _edited: true } : {}),
        },
      },
    }))
  }

  const saveAll = async () => {
    setSaving(true)
    setError('')
    setMsg('')
    try {
      for (const plan of data?.plans || []) {
        const currencies = data?.supported_currencies || []
        const gbpDraft = drafts?.[plan.plan_id]?.GBP
        if (gbpDraft) {
          await apiFetch(`/admin/pricing/plan-prices/${encodeURIComponent(plan.plan_id)}/GBP`, {
            method: 'PUT',
            body: JSON.stringify({
              monthly_price_minor: gbpDraft.monthly === '' ? null : poundsToPence(gbpDraft.monthly),
              per_min_minor: poundsToPence(gbpDraft.perMin),
              extra_per_min_minor: poundsToPence(gbpDraft.extraPerMin),
            }),
          })
        }
        for (const currency of currencies) {
          if (currency === 'GBP') continue
          const draft = drafts?.[plan.plan_id]?.[currency]
          if (!draft) continue
          if (!draft._edited && !draft.manual_override) continue
          await apiFetch(`/admin/pricing/plan-prices/${encodeURIComponent(plan.plan_id)}/${currency}`, {
            method: 'PUT',
            body: JSON.stringify({
              monthly_price_minor: draft.monthly === '' ? null : poundsToPence(draft.monthly),
              per_min_minor: poundsToPence(draft.perMin),
              extra_per_min_minor: poundsToPence(draft.extraPerMin),
            }),
          })
        }
      }
      await load()
      setMsg('Plan prices saved. GBP synced unlocked FX markets.')
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
      description="GBP is the authoring default. Other currencies sync from FX unless marked manual."
      onRetry={load}
    >
      {data ? (
        <PricingPageFrame
          title="Plan prices"
          description="Set GBP prices to sync unlocked markets. Edit another currency to lock a market-specific price."
          error={error}
          msg={msg}
          actions={
            <Button size="sm" className="h-8" type="button" disabled={saving} onClick={() => void saveAll()}>
              {saving ? 'Saving…' : 'Save all prices'}
            </Button>
          }
        >
          <div className="pricingPlanPricesStack">
            {(data.plans || []).map((plan) => (
              <div key={plan.plan_id} className="pricingPlanPriceCard">
                <div className="pricingPlanPriceHead">
                  <strong>{plan.plan_name}</strong>
                  <span className="muted">{plan.plan_code}</span>
                  {plan.is_enterprise ? <Pill tone="info">Enterprise — custom pricing</Pill> : null}
                  {!plan.is_active ? <Pill tone="warning">Inactive</Pill> : null}
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
