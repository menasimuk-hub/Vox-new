import React from 'react'
import { usePricingSettings } from './pricingUtils'
import PricingPageFrame, { PricingField } from './PricingPageFrame'

export default function PricingEstimator() {
  const { settings, setSettings, loading, error, msg, save } = usePricingSettings()
  if (loading || !settings) return <p className="muted">Loading…</p>
  const set = (field, value) => setSettings({ ...settings, [field]: Number(value || 0) })

  return (
    <PricingPageFrame title="Estimator defaults" description="Default slider values on customer Packages page." error={error} msg={msg}>
      <div className="pricingGrid5">
        <PricingField label="Duration (min)" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" min="1" value={settings.estimator_default_duration_min} onChange={(e) => set('estimator_default_duration_min', e.target.value)} />
        </PricingField>
        <PricingField label="Interviews" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" min="1" value={settings.estimator_default_interview_count} onChange={(e) => set('estimator_default_interview_count', e.target.value)} />
        </PricingField>
      </div>
      <div className="pricingActions"><button className="btn" type="button" onClick={() => void save(settings)}>Save</button></div>
    </PricingPageFrame>
  )
}
