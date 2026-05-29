import React from 'react'
import { usePricingSettings, penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingField } from './PricingPageFrame'

export default function PricingServices() {
  const { settings, setSettings, loading, error, msg, save } = usePricingSettings()
  if (loading || !settings) return <p className="muted">Loading…</p>
  const set = (field, value) => setSettings({ ...settings, [field]: value })

  return (
    <PricingPageFrame title="Service rates" description="Fixed unit prices for PAYG and for calculating plan WA/CV allowances." error={error} msg={msg}>
      <div className="pricingGrid5">
        <PricingField label="Interview /min £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(settings.interview_per_min_pence)} onChange={(e) => set('interview_per_min_pence', poundsToPence(e.target.value))} />
        </PricingField>
        <PricingField label="WA send £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(settings.whatsapp_survey_fee_pence)} onChange={(e) => set('whatsapp_survey_fee_pence', poundsToPence(e.target.value))} />
        </PricingField>
        <PricingField label="ATS scan £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(settings.ats_cv_scan_fee_pence)} onChange={(e) => set('ats_cv_scan_fee_pence', poundsToPence(e.target.value))} />
        </PricingField>
      </div>
      <div className="pricingActions"><button className="btn" type="button" onClick={() => void save(settings)}>Save</button></div>
    </PricingPageFrame>
  )
}
