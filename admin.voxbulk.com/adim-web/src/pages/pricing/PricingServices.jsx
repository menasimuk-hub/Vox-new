import React from 'react'
import { usePricingSettings, penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingField, PricingLoadGate } from './PricingPageFrame'

export default function PricingServices() {
  const { settings, setSettings, loading, error, msg, save, load } = usePricingSettings()
  const set = (field, value) => setSettings({ ...settings, [field]: value })
  const waPkg = settings?.wa_survey_package_fee_pence ?? settings?.whatsapp_survey_fee_pence
  const waExtra = settings?.wa_survey_extra_pence ?? 49

  return (
    <PricingLoadGate
      loading={loading}
      error={error}
      title="Service rates"
      description="Fixed unit prices for PAYG and for calculating plan WA/CV allowances."
      onRetry={load}
    >
      {settings ? (
      <PricingPageFrame title="Service rates" description="Fixed unit prices for PAYG and for calculating plan WA/CV allowances." error={error} msg={msg}>
        <div className="pricingGrid5">
          <PricingField label="Interview /min £" compact>
            <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(settings.interview_per_min_pence)} onChange={(e) => set('interview_per_min_pence', poundsToPence(e.target.value))} />
          </PricingField>
          <PricingField label="WA package fee £" compact>
            <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(waPkg)} onChange={(e) => set('wa_survey_package_fee_pence', poundsToPence(e.target.value))} />
          </PricingField>
          <PricingField label="WA extra £" compact>
            <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(waExtra)} onChange={(e) => set('wa_survey_extra_pence', poundsToPence(e.target.value))} />
          </PricingField>
          <PricingField label="ATS scan £" compact>
            <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={penceToPounds(settings.ats_cv_scan_fee_pence)} onChange={(e) => set('ats_cv_scan_fee_pence', poundsToPence(e.target.value))} />
          </PricingField>
        </div>
        <p className="muted text-sm">Plan includes = plan price ÷ WA package fee. Extra recipients billed at WA extra rate after allowance is used.</p>
        <div className="pricingActions"><button className="btn" type="button" onClick={() => void save(settings)}>Save</button></div>
      </PricingPageFrame>
      ) : null}
    </PricingLoadGate>
  )
}
