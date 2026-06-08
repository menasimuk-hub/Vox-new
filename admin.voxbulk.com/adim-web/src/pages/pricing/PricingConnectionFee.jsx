import React from 'react'
import { usePricingSettings, penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingField, PricingLoadGate } from './PricingPageFrame'

export default function PricingConnectionFee() {
  const { settings, setSettings, loading, error, msg, save, load } = usePricingSettings()
  const set = (field, value) => setSettings({ ...settings, [field]: value })

  return (
    <PricingLoadGate
      loading={loading}
      error={error}
      title="Connection fee"
      description="Flat fee per AI call, on top of per-minute usage."
      onRetry={load}
      ready={Boolean(settings)}
    >
      <PricingPageFrame title="Connection fee" description="Flat fee per AI call, on top of per-minute usage." error={error} msg={msg}>
      <div className="pricingGrid5">
        <PricingField label="Enabled" compact>
          <label className="svcPriceToggle" style={{ marginTop: 6 }}><input type="checkbox" checked={Boolean(settings.connection_fee_enabled)} onChange={(e) => set('connection_fee_enabled', e.target.checked)} /><span className="svcPriceToggleUi" /></label>
        </PricingField>
        <PricingField label="Fee (GBP)" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(settings.connection_fee_pence)} onChange={(e) => set('connection_fee_pence', poundsToPence(e.target.value))} />
        </PricingField>
        <PricingField label="Customer label" compact wide fullRow>
          <input className="input pricingInputSm" value={settings.connection_fee_label || ''} onChange={(e) => set('connection_fee_label', e.target.value)} />
        </PricingField>
      </div>
      <div className="pricingActions"><button className="btn" type="button" onClick={() => void save(settings)}>Save</button></div>
      </PricingPageFrame>
    </PricingLoadGate>
  )
}
