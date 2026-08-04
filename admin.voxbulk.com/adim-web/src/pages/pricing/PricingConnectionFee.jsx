import React from 'react'
import { usePricingSettings, penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingField, PricingLoadGate } from './PricingPageFrame'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Switch } from '@/components/ui/Switch'

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
    >
      {settings ? (
        <PricingPageFrame
          title="Connection fee"
          description="Flat fee per AI call, on top of per-minute usage."
          error={error}
          msg={msg}
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <PricingField label="Enabled" compact>
              <div className="pt-1">
                <Switch
                  checked={Boolean(settings.connection_fee_enabled)}
                  onCheckedChange={(checked) => set('connection_fee_enabled', checked)}
                  aria-label="Connection fee enabled"
                />
              </div>
            </PricingField>
            <PricingField label="Fee (GBP)" compact>
              <Input
                className="h-8"
                type="number"
                step="0.01"
                value={penceToPounds(settings.connection_fee_pence)}
                onChange={(e) => set('connection_fee_pence', poundsToPence(e.target.value))}
              />
            </PricingField>
            <PricingField label="Customer label" compact wide fullRow>
              <Input
                className="h-8"
                value={settings.connection_fee_label || ''}
                onChange={(e) => set('connection_fee_label', e.target.value)}
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
