import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import PricingPageFrame, { PricingField, PricingLoadGate } from './PricingPageFrame'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Switch } from '@/components/ui/Switch'

export default function PricingInvoiceSettings() {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const body = await apiFetch('/admin/pricing/billing-settings')
      setSettings(body)
      return true
    } catch (e) {
      setError(e?.message || 'Could not load billing settings')
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

  const set = (key, value) => setSettings((s) => ({ ...s, [key]: value }))

  const save = async () => {
    setSaving(true)
    setError('')
    setMsg('')
    try {
      const body = await apiFetch('/admin/pricing/billing-settings', {
        method: 'PUT',
        body: JSON.stringify({
          company_name: settings.company_name,
          company_address: settings.company_address,
          company_email: settings.company_email,
          company_phone: settings.company_phone,
          vat_number: settings.vat_number,
          vat_enabled: Boolean(settings.vat_enabled),
          invoice_prefix: settings.invoice_prefix,
          invoice_next_number: Number(settings.invoice_next_number || 1),
          invoice_due_days: Number(settings.invoice_due_days || 7),
        }),
      })
      setSettings(body)
      setMsg('Billing settings saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <PricingLoadGate
      loading={loading}
      error={!settings ? error : ''}
      title="Invoice settings"
      description="Company details, VAT, and invoice numbering used on every customer invoice."
      onRetry={load}
    >
      {settings ? (
        <PricingPageFrame
          title="Invoice settings"
          description="Company details, VAT, and invoice numbering used on every customer invoice PDF and email."
          error={error}
          msg={msg}
          actions={
            <Button size="sm" className="h-8" type="button" disabled={saving} onClick={() => void save()}>
              {saving ? 'Saving…' : 'Save settings'}
            </Button>
          }
        >
          <h3 className="text-[12px] font-semibold text-foreground">Company details</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <PricingField label="Company name" wide>
              <Input className="h-8" value={settings.company_name || ''} onChange={(e) => set('company_name', e.target.value)} />
            </PricingField>
            <PricingField label="Billing email" wide>
              <Input className="h-8" type="email" value={settings.company_email || ''} onChange={(e) => set('company_email', e.target.value)} placeholder="billing@voxbulk.com" />
            </PricingField>
            <PricingField label="Phone">
              <Input className="h-8" value={settings.company_phone || ''} onChange={(e) => set('company_phone', e.target.value)} />
            </PricingField>
          </div>
          <PricingField label="Registered address" fullRow>
            <Textarea rows={3} value={settings.company_address || ''} onChange={(e) => set('company_address', e.target.value)} />
          </PricingField>

          <h3 className="text-[12px] font-semibold text-foreground">VAT</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <PricingField label="VAT registered" compact>
              <div className="flex items-center gap-2 pt-1">
                <Switch
                  checked={Boolean(settings.vat_enabled)}
                  onCheckedChange={(checked) => set('vat_enabled', checked)}
                  aria-label="Charge VAT on invoices"
                />
                <span className="text-xs text-muted-foreground">Charge VAT on invoices</span>
              </div>
            </PricingField>
            <PricingField label="VAT number" wide>
              <Input className="h-8" value={settings.vat_number || ''} onChange={(e) => set('vat_number', e.target.value)} placeholder="GB123456789" />
            </PricingField>
          </div>
          <p className="m-0 text-xs text-muted-foreground">
            When enabled, UK customers are charged 20% VAT. Customers outside the UK are zero-rated unless a country rate is configured.
          </p>

          <h3 className="text-[12px] font-semibold text-foreground">Invoice numbering</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <PricingField label="Prefix" compact hint="e.g. INV → INV-2026-000123">
              <Input className="h-8" value={settings.invoice_prefix || ''} onChange={(e) => set('invoice_prefix', e.target.value)} />
            </PricingField>
            <PricingField label="Next number" compact>
              <Input className="h-8" type="number" min="1" value={settings.invoice_next_number ?? 1} onChange={(e) => set('invoice_next_number', e.target.value)} />
            </PricingField>
            <PricingField label="Due days" compact hint="Days until a Direct Debit invoice is due">
              <Input className="h-8" type="number" min="0" value={settings.invoice_due_days ?? 7} onChange={(e) => set('invoice_due_days', e.target.value)} />
            </PricingField>
          </div>
        </PricingPageFrame>
      ) : null}
    </PricingLoadGate>
  )
}
