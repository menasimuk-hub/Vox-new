import React from 'react'
import { usePricingSettings, penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingField, PricingLoadGate } from './PricingPageFrame'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

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
        <PricingPageFrame
          title="Service rates"
          description="Fixed unit prices for PAYG and for calculating plan WA/CV allowances."
          error={error}
          msg={msg}
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <PricingField label="Interview /min £" compact>
              <Input
                className="h-8"
                type="number"
                step="0.01"
                value={penceToPounds(settings.interview_per_min_pence)}
                onChange={(e) => set('interview_per_min_pence', poundsToPence(e.target.value))}
              />
            </PricingField>
            <PricingField label="WA package fee £" compact>
              <Input
                className="h-8"
                type="number"
                step="0.01"
                value={penceToPounds(waPkg)}
                onChange={(e) => {
                  const pence = poundsToPence(e.target.value)
                  setSettings({ ...settings, wa_survey_package_fee_pence: pence, whatsapp_survey_fee_pence: pence })
                }}
              />
            </PricingField>
            <PricingField label="WA extra £" compact>
              <Input
                className="h-8"
                type="number"
                step="0.01"
                value={penceToPounds(waExtra)}
                onChange={(e) => set('wa_survey_extra_pence', poundsToPence(e.target.value))}
              />
            </PricingField>
            <PricingField label="ATS scan £" compact>
              <Input
                className="h-8"
                type="number"
                step="0.01"
                value={penceToPounds(settings.ats_cv_scan_fee_pence)}
                onChange={(e) => set('ats_cv_scan_fee_pence', poundsToPence(e.target.value))}
              />
            </PricingField>
          </div>
          <p className="text-[12px] text-muted-foreground">
            Plan includes = plan price ÷ WA package fee. Extra recipients billed at WA extra rate after allowance is
            used.
          </p>
          <div className="pt-1">
            <Button type="button" size="sm" className="h-8" onClick={() => void save(settings)}>
              Save
            </Button>
          </div>
        </PricingPageFrame>
      ) : null}
    </PricingLoadGate>
  )
}
