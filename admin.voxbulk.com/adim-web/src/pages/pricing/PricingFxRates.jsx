import React from 'react'
import { usePricingSettings } from './pricingUtils'
import PricingPageFrame, { PricingField } from './PricingPageFrame'

export default function PricingFxRates() {
  const { settings, setSettings, loading, error, msg, save } = usePricingSettings()
  if (loading || !settings) return <p className="muted">Loading…</p>
  const set = (field, value) => setSettings({ ...settings, [field]: Number(value || 0) })

  return (
    <PricingPageFrame title="FX rates" description="GBP base — multiply for AUD, CAD, USD on customer dashboard." error={error} msg={msg}>
      <div className="pricingGrid5">
        <PricingField label="AUD ×" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={settings.fx_aud_multiplier} onChange={(e) => set('fx_aud_multiplier', e.target.value)} />
        </PricingField>
        <PricingField label="CAD ×" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={settings.fx_cad_multiplier} onChange={(e) => set('fx_cad_multiplier', e.target.value)} />
        </PricingField>
        <PricingField label="USD ×" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={settings.fx_usd_multiplier} onChange={(e) => set('fx_usd_multiplier', e.target.value)} />
        </PricingField>
      </div>
      <div className="pricingActions"><button className="btn" type="button" onClick={() => void save(settings)}>Save</button></div>
    </PricingPageFrame>
  )
}
