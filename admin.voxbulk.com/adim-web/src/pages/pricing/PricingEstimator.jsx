import React from 'react'
import { usePricingSettings } from './pricingUtils'
import PricingPageFrame, { PricingField, PricingLoadGate } from './PricingPageFrame'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export default function PricingEstimator() {
  const { settings, setSettings, loading, error, msg, save, load } = usePricingSettings()
  const set = (field, value) => setSettings({ ...settings, [field]: Number(value || 0) })

  return (
    <PricingLoadGate
      loading={loading}
      error={error}
      title="Estimator defaults"
      description="Default slider values on customer Packages page."
      onRetry={load}
    >
      {settings ? (
        <PricingPageFrame
          title="Estimator defaults"
          description="Default slider values on customer Packages page."
          error={error}
          msg={msg}
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <PricingField label="Duration (min)" compact>
              <Input
                className="h-8"
                type="number"
                min="1"
                value={settings.estimator_default_duration_min}
                onChange={(e) => set('estimator_default_duration_min', e.target.value)}
              />
            </PricingField>
            <PricingField label="Interviews" compact>
              <Input
                className="h-8"
                type="number"
                min="1"
                value={settings.estimator_default_interview_count}
                onChange={(e) => set('estimator_default_interview_count', e.target.value)}
              />
            </PricingField>
          </div>
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
