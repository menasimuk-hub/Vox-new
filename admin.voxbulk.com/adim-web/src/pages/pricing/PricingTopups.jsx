import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingField, PricingLoadGate } from './PricingPageFrame'

const emptyTier = { credit_gbp_pence: 5000, bonus_credit_pence: 0, is_active: true, sort_order: 100 }

function BoxInput({ value, onBlur, step }) {
  return (
    <div className="pricingCellBox">
      <input className="input pricingInputInline" type="number" step={step || '1'} defaultValue={value} onBlur={onBlur} />
    </div>
  )
}

export default function PricingTopups() {
  const [tiers, setTiers] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [draft, setDraft] = useState(emptyTier)

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const rows = await apiFetch('/admin/pricing/topup-tiers')
      setTiers(Array.isArray(rows) ? rows : [])
      return true
    } catch (e) {
      setLoadError(e?.message || 'Load failed')
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

  const reload = useCallback(async () => {
    setLoading(true)
    await load()
    setLoading(false)
  }, [load])

  const saveTier = async (tier) => {
    setError('')
    try {
      await apiFetch(`/admin/pricing/topup-tiers/${encodeURIComponent(tier.id)}`, { method: 'PUT', body: JSON.stringify(tier) })
      await load()
      setMsg('Saved.')
    } catch (e) { setError(e?.message || 'Save failed') }
  }

  const addTier = async () => {
    setError('')
    try {
      await apiFetch('/admin/pricing/topup-tiers', { method: 'POST', body: JSON.stringify({ ...draft, credit_gbp_pence: poundsToPence(penceToPounds(draft.credit_gbp_pence)), bonus_credit_pence: poundsToPence(penceToPounds(draft.bonus_credit_pence)) }) })
      setDraft(emptyTier)
      await load()
      setMsg('Tier added.')
    } catch (e) { setError(e?.message || 'Add failed') }
  }

  const removeTier = async (id) => {
    if (!window.confirm('Delete tier?')) return
    await apiFetch(`/admin/pricing/topup-tiers/${encodeURIComponent(id)}`, { method: 'DELETE' })
    await load()
  }

  return (
    <PricingLoadGate
      loading={loading}
      error={loadError}
      title="Top-up tiers"
      description="Fixed wallet amounts. Customers can also enter any amount ≥ £5."
      onRetry={reload}
    >
      <PricingPageFrame title="Top-up tiers" description="Fixed wallet amounts. Customers can also enter any amount ≥ £5." error={error} msg={msg}>
      <div className="tableWrap pricingTableWrap">
        <table className="table pricingTable pricingTablePlans">
          <thead>
            <tr>
              <th className="pricingThNum">Credit £</th>
              <th className="pricingThNum">Bonus £</th>
              <th className="pricingThNum pricingThCalc">Total £</th>
              <th className="pricingThNum">Order</th>
              <th className="pricingThToggle">On</th>
              <th className="pricingThAction" />
            </tr>
          </thead>
          <tbody>
            {tiers.map((t) => (
              <tr key={t.id} className="pricingPlanRow">
                <td className="pricingTdNum"><BoxInput value={penceToPounds(t.credit_gbp_pence)} step="0.01" onBlur={(e) => void saveTier({ ...t, credit_gbp_pence: poundsToPence(e.target.value) })} /></td>
                <td className="pricingTdNum"><BoxInput value={penceToPounds(t.bonus_credit_pence)} step="0.01" onBlur={(e) => void saveTier({ ...t, bonus_credit_pence: poundsToPence(e.target.value) })} /></td>
                <td className="pricingTdNum"><span className="pricingCellBox calc">{penceToPounds((t.credit_gbp_pence || 0) + (t.bonus_credit_pence || 0))}</span></td>
                <td className="pricingTdNum"><BoxInput value={t.sort_order} onBlur={(e) => void saveTier({ ...t, sort_order: Number(e.target.value || 0) })} /></td>
                <td className="pricingTdCenter"><input type="checkbox" defaultChecked={t.is_active} onChange={(e) => void saveTier({ ...t, is_active: e.target.checked })} /></td>
                <td className="pricingTdCenter"><button className="btn soft pricingSaveBtn" type="button" onClick={() => void removeTier(t.id)}>Del</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="pricingSectionLabel" style={{ marginTop: 16 }}>Add tier</p>
      <div className="pricingGrid5">
        <PricingField label="Credit £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(draft.credit_gbp_pence)} onChange={(e) => setDraft({ ...draft, credit_gbp_pence: poundsToPence(e.target.value) })} />
        </PricingField>
        <PricingField label="Bonus £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(draft.bonus_credit_pence)} onChange={(e) => setDraft({ ...draft, bonus_credit_pence: poundsToPence(e.target.value) })} />
        </PricingField>
        <div className="pricingActions" style={{ gridColumn: 'span 1', alignSelf: 'end' }}>
          <button className="btn" type="button" onClick={() => void addTier()}>Add</button>
        </div>
      </div>
      </PricingPageFrame>
    </PricingLoadGate>
  )
}
