import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import PricingPageFrame, { PricingLoadGate } from './PricingPageFrame'
import { penceToPounds, poundsToPence } from './pricingUtils'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'

const RATE_FIELDS = [
  ['connection_fee_minor', 'Connection fee / call'],
  ['interview_per_min_minor', 'AI call / interview per min'],
  ['wa_package_fee_minor', 'WA survey per recipient (plan)'],
  ['wa_extra_minor', 'WA survey extra / PAYG'],
  ['cv_scan_fee_minor', 'CV scan fee'],
]

const FX_QUOTES = ['EUR', 'USD', 'CAD', 'AUD']

export default function PricingCurrencyRates() {
  const [rows, setRows] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [fxDrafts, setFxDrafts] = useState({})
  const [dirtyUnit, setDirtyUnit] = useState({})
  const [dirtyFx, setDirtyFx] = useState({})
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
      setDirtyUnit({})
      const fxNext = {}
      for (const r of body.fx_rates || []) {
        fxNext[r.quote_currency] = String(r.rate ?? '')
      }
      for (const q of FX_QUOTES) {
        if (fxNext[q] == null) fxNext[q] = ''
      }
      setFxDrafts(fxNext)
      setDirtyFx({})
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
    setDirtyUnit((s) => ({ ...s, [currency]: true }))
  }

  const setFx = (quote, value) => {
    setFxDrafts((s) => ({ ...s, [quote]: value }))
    setDirtyFx((s) => ({ ...s, [quote]: true }))
  }

  const saveAll = async () => {
    setSaving(true)
    setError('')
    setMsg('')
    try {
      if (Object.keys(dirtyFx).some((k) => dirtyFx[k])) {
        const rates = {}
        for (const q of FX_QUOTES) {
          const n = Number(fxDrafts[q])
          if (!Number.isFinite(n) || n <= 0) throw new Error(`FX rate for ${q} must be a positive number`)
          rates[q] = n
        }
        await apiFetch('/admin/pricing/fx-rates', {
          method: 'PUT',
          body: JSON.stringify({ rates }),
        })
      }

      // Always save GBP when any unit rate changed (or when only FX changed, re-sync from current GBP).
      const gbpDraft = drafts.GBP || {}
      await apiFetch('/admin/pricing/currency-settings/GBP', {
        method: 'PUT',
        body: JSON.stringify(Object.fromEntries(RATE_FIELDS.map(([key]) => [key, poundsToPence(gbpDraft[key])]))),
      })

      for (const row of rows || []) {
        if (row.currency === 'GBP') continue
        if (!dirtyUnit[row.currency]) continue
        const draft = drafts[row.currency] || {}
        const payload = Object.fromEntries(RATE_FIELDS.map(([key]) => [key, poundsToPence(draft[key])]))
        await apiFetch(`/admin/pricing/currency-settings/${row.currency}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      }

      await load()
      setMsg('Saved. GBP unit rates updated; other unlocked currencies synced from GBP via FX. Manual markets kept.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const resyncUnlocked = async () => {
    setSaving(true)
    setError('')
    setMsg('')
    try {
      await apiFetch('/admin/pricing/fx-rates/sync-unit-rates', {
        method: 'POST',
        body: JSON.stringify({ force: false }),
      })
      await load()
      setMsg('Re-synced unlocked currencies from GBP.')
    } catch (e) {
      setError(e?.message || 'Sync failed')
    } finally {
      setSaving(false)
    }
  }

  const ordered = [...(rows || [])].sort((a, b) => {
    if (a.currency === 'GBP') return -1
    if (b.currency === 'GBP') return 1
    return String(a.currency).localeCompare(String(b.currency))
  })

  return (
    <PricingLoadGate
      loading={loading}
      error={!rows ? error : ''}
      title="Currency rates"
      description="GBP is the default. Other markets sync from GBP using the FX rates below unless you edit them by hand."
      onRetry={load}
    >
      {rows ? (
        <PricingPageFrame
          title="Currency rates"
          description="Edit GBP first. Unlocked markets sync from FX when you save. Editing EUR/USD/CAD/AUD locks that market until you re-sync unlocked from GBP."
          error={error}
          msg={msg}
          actions={
            <>
              <Button size="sm" className="h-8" type="button" variant="outline" disabled={saving} onClick={() => void resyncUnlocked()}>
                Re-sync unlocked from GBP
              </Button>
              <Button size="sm" className="h-8" type="button" disabled={saving} onClick={() => void saveAll()}>
                {saving ? 'Saving…' : 'Save rates'}
              </Button>
            </>
          }
        >
          <h3 className="pricingPkgPricesTitle" style={{ marginTop: 0 }}>FX rates (1 GBP =)</h3>
          <p className="pricingShellIntro" style={{ marginBottom: 12 }}>
            Seeded for today — change anytime. Used only to fill catalog unit rates, not at checkout.
          </p>
          <table className="pricingPlanPriceTable" style={{ marginBottom: 24 }}>
            <thead>
              <tr>
                <th>Quote</th>
                {FX_QUOTES.map((q) => (
                  <th key={q}>{q}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Rate</strong></td>
                {FX_QUOTES.map((q) => (
                  <td key={q}>
                    <Input
                      className="h-8"
                      type="number"
                      step="0.0001"
                      min="0"
                      value={fxDrafts[q] ?? ''}
                      onChange={(e) => setFx(q, e.target.value)}
                    />
                  </td>
                ))}
              </tr>
            </tbody>
          </table>

          <h3 className="pricingPkgPricesTitle">Unit rates</h3>
          <table className="pricingPlanPriceTable">
            <thead>
              <tr>
                <th>Rate</th>
                {ordered.map((row) => (
                  <th key={row.currency}>
                    {CURRENCY_SYMBOLS[row.currency] || ''} {row.currency}
                    {row.currency === 'GBP' ? ' (default)' : row.manual_override ? ' · manual' : ' · FX'}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {RATE_FIELDS.map(([key, label]) => (
                <tr key={key}>
                  <td><strong>{label}</strong></td>
                  {ordered.map((row) => (
                    <td key={row.currency}>
                      <Input
                        className="h-8"
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
