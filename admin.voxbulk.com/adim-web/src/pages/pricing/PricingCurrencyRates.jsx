import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import PricingPageFrame, { PricingLoadGate } from './PricingPageFrame'
import { penceToPounds, poundsToPence } from './pricingUtils'

const CURRENCY_SYMBOLS = { GBP: '£', USD: '$', CAD: 'CA$', AUD: 'A$' }

const RATE_FIELDS = [
  ['connection_fee_minor', 'Connection fee / call'],
  ['interview_per_min_minor', 'AI call / interview per min'],
  ['wa_package_fee_minor', 'WA survey per recipient (plan)'],
  ['wa_extra_minor', 'WA survey extra / PAYG'],
  ['cv_scan_fee_minor', 'CV scan fee'],
]

export default function PricingCurrencyRates() {
  const [rows, setRows] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const body = await apiFetch('/admin/pricing/currency-settings')
      const settings = body.currency_settings || []
      setRows(settings)
      const next = {}
      for (const row of settings) {
        next[row.currency] = Object.fromEntries(RATE_FIELDS.map(([key]) => [key, penceToPounds(row[key])]))
      }
      setDrafts(next)
      return true
    } catch (e) {
      setError(e?.message || 'Could not load currency rates')
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

  const setDraft = (currency, key, value) => {
    setDrafts((s) => ({ ...s, [currency]: { ...(s[currency] || {}), [key]: value } }))
  }

  const saveAll = async () => {
    setSaving(true)
    setError('')
    setMsg('')
    try {
      for (const row of rows || []) {
        const draft = drafts[row.currency] || {}
        const payload = Object.fromEntries(RATE_FIELDS.map(([key]) => [key, poundsToPence(draft[key])]))
        await apiFetch(`/admin/pricing/currency-settings/${row.currency}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      }
      await load()
      setMsg('Currency rates saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <PricingLoadGate
      loading={loading}
      error={!rows ? error : ''}
      title="Currency rates"
      description="Per-currency service unit rates — set each market price explicitly."
      onRetry={load}
    >
      {rows ? (
        <PricingPageFrame
          title="Currency rates"
          description="Unit rates per currency for PAYG and overage billing. There is no FX conversion — each market price is set here."
          error={error}
          msg={msg}
          actions={
            <button className="btn primary" type="button" disabled={saving} onClick={() => void saveAll()}>
              {saving ? 'Saving…' : 'Save all rates'}
            </button>
          }
        >
          <table className="pricingPlanPriceTable">
            <thead>
              <tr>
                <th>Rate</th>
                {rows.map((row) => (
                  <th key={row.currency}>{CURRENCY_SYMBOLS[row.currency] || ''} {row.currency}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {RATE_FIELDS.map(([key, label]) => (
                <tr key={key}>
                  <td><strong>{label}</strong></td>
                  {rows.map((row) => (
                    <td key={row.currency}>
                      <input
                        className="input pricingInputSm pricingInputNum"
                        type="number"
                        step="0.01"
                        min="0"
                        value={drafts?.[row.currency]?.[key] ?? ''}
                        onChange={(e) => setDraft(row.currency, key, e.target.value)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </PricingPageFrame>
      ) : null}
    </PricingLoadGate>
  )
}
