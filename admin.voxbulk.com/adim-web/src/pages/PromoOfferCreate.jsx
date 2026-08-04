import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PlanPickerSelect from '../components/billing/PlanPickerSelect'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'

const SERVICES = [
  { value: 'voxbulk', label: 'Core subscription' },
  { value: 'survey', label: 'Survey' },
  { value: 'interview', label: 'Interview' },
  { value: 'customer_feedback', label: 'Customer Feedback' },
  { value: 'expo', label: 'Expo' },
]

const BENEFITS = [
  { value: 'free_usage', label: 'Free usage' },
  { value: 'discount', label: 'Discount (% or £)' },
]

const REDEEM_MODES = [
  { value: 'anyone', label: 'Anyone with the code (signup or Dashboard)' },
  { value: 'signup_only', label: 'Signup only' },
  { value: 'admin_only', label: 'Admin apply only' },
]

const emptyDraft = {
  code: '',
  name: '',
  service_kind: 'survey',
  benefit_kind: 'free_usage',
  plan_code: '',
  usage_amount: 20,
  trial_days: 15,
  discount_type: 'percent',
  discount_value: 20,
  redeem_mode: 'anyone',
  max_redemptions: 10,
  expires_in_days: 30,
  prospect_name: '',
  prospect_email: '',
  prospect_phone: '',
}

const planPickerClass =
  'flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-[12px] shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

function usageLabel(service) {
  if (service === 'survey') return 'Free survey contacts'
  if (service === 'interview') return 'Free interviews'
  if (service === 'customer_feedback') return 'Free Feedback units'
  if (service === 'expo') return 'Free Expo days'
  return 'Trial days'
}

export default function PromoOfferCreate() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState(emptyDraft)
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState(null)
  const [orgQuery, setOrgQuery] = useState('')
  const [orgs, setOrgs] = useState([])
  const [selectedOrgIds, setSelectedOrgIds] = useState([])
  const [applying, setApplying] = useState(false)
  const [applyResult, setApplyResult] = useState(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/admin/plans')
        if (!cancelled) setPlans(Array.isArray(data) ? data : data?.items || [])
      } catch {
        if (!cancelled) setPlans([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const corePlans = useMemo(
    () =>
      (plans || []).filter((p) => {
        const kind = String(p.service_kind || p.service_code || 'voxbulk').toLowerCase()
        return kind === 'voxbulk' || kind === 'dental' || !kind
      }),
    [plans],
  )

  const setField = (key, value) => setDraft((d) => ({ ...d, [key]: value }))

  const previewLine = useMemo(() => {
    if (draft.benefit_kind === 'discount') {
      if (draft.discount_type === 'percent') {
        return `${draft.discount_value || 0}% off next ${draft.service_kind.replace('_', ' ')} checkout`
      }
      return `£${(Number(draft.discount_value || 0) / 100).toFixed(2)} off next ${draft.service_kind.replace('_', ' ')} checkout`
    }
    if (draft.service_kind === 'voxbulk') {
      return `${draft.trial_days || draft.usage_amount || 0}-day Core trial`
    }
    return `${draft.usage_amount || 0} × ${usageLabel(draft.service_kind).toLowerCase()}`
  }, [draft])

  const onSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = {
        code: draft.code || undefined,
        name: draft.name || undefined,
        service_kind: draft.service_kind,
        benefit_kind: draft.benefit_kind,
        redeem_mode: draft.redeem_mode,
        max_redemptions: Number(draft.max_redemptions) || 1,
        expires_in_days: Number(draft.expires_in_days) || 30,
        prospect_name: draft.prospect_name || undefined,
        prospect_email: draft.prospect_email || undefined,
        prospect_phone: draft.prospect_phone || undefined,
      }
      if (draft.benefit_kind === 'discount') {
        payload.discount_type = draft.discount_type
        payload.discount_value =
          draft.discount_type === 'fixed_minor'
            ? Math.round(Number(draft.discount_value) || 0)
            : Number(draft.discount_value) || 0
        if (draft.discount_type === 'fixed_minor' && payload.discount_value < 100) {
          // Allow entering pounds in the UI when value looks like pounds (< 100 with type fixed) — treat as pounds.
          // Prefer pence input: if user typed 20 with fixed, convert pounds→pence when < 500 and no decimals intent.
        }
      } else {
        payload.usage_amount = Number(draft.usage_amount) || 0
        if (draft.service_kind === 'voxbulk') {
          payload.plan_code = draft.plan_code || 'starter'
          payload.trial_days = Number(draft.trial_days) || Number(draft.usage_amount) || 15
          payload.usage_amount = payload.trial_days
        }
        if (draft.service_kind === 'expo') {
          payload.trial_days = Number(draft.usage_amount) || 3
        }
        if (draft.service_kind === 'survey') payload.survey_contacts_included = payload.usage_amount
        if (draft.service_kind === 'interview') payload.interview_contacts_included = payload.usage_amount
      }
      if (draft.benefit_kind === 'discount' && draft.discount_type === 'fixed_minor') {
        // UI stores pounds in discount_value_pounds field via discount_value when type fixed — convert £ to pence
        const pounds = Number(draft.discount_value)
        payload.discount_value = Math.round(pounds * 100)
      }
      const res = await apiFetch('/admin/promo-offers', { method: 'POST', body: JSON.stringify(payload) })
      setCreated(res.promo)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create promo')
    } finally {
      setSaving(false)
    }
  }

  const searchOrgs = async () => {
    try {
      const data = await apiFetch(`/admin/organisations?search=${encodeURIComponent(orgQuery || '')}&limit=30`)
      setOrgs(Array.isArray(data) ? data : data?.items || data?.organisations || [])
    } catch {
      setOrgs([])
    }
  }

  const toggleOrg = (id) => {
    setSelectedOrgIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const applyToOrgs = async () => {
    if (!created?.id || selectedOrgIds.length === 0) return
    setApplying(true)
    setApplyResult(null)
    try {
      const res = await apiFetch(`/admin/promo-offers/${created.id}/apply`, {
        method: 'POST',
        body: JSON.stringify({ org_ids: selectedOrgIds }),
      })
      setApplyResult(res)
    } catch (err) {
      setApplyResult({ ok: false, error: err instanceof Error ? err.message : 'Apply failed' })
    } finally {
      setApplying(false)
    }
  }

  if (loading) {
    return (
      <div className="ds-scope space-y-4">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    )
  }

  if (created) {
    return (
      <div className="ds-scope mx-auto max-w-[720px] space-y-4">
        <div>
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Promo created</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            {created.benefit_summary || previewLine}
          </p>
        </div>

        <Panel title="Offer details" bodyClassName="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] text-muted-foreground">Code</span>
            <Pill tone="info">{created.code}</Pill>
          </div>
          <div className="text-[13px] text-foreground">
            <span className="font-semibold">Signup link:</span>{' '}
            <a
              href={created.signup_url}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline break-all"
            >
              {created.signup_url}
            </a>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => navigator.clipboard?.writeText(created.signup_url || created.code)}
          >
            Copy link
          </Button>
        </Panel>

        <Panel
          title="Apply to organisations"
          subtitle="Select one or more orgs to apply this promo now (Admin apply)."
          bodyClassName="space-y-3"
        >
          <div className="flex gap-2">
            <Input
              placeholder="Search organisations"
              value={orgQuery}
              onChange={(e) => setOrgQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void searchOrgs()
                }
              }}
              className="h-8 flex-1"
            />
            <Button variant="outline" size="sm" className="h-8" onClick={() => void searchOrgs()}>
              Search
            </Button>
          </div>
          <div className="max-h-60 overflow-auto rounded-md border border-border bg-surface-muted/30 p-2">
            {orgs.length === 0 ? (
              <p className="p-2 text-[13px] text-muted-foreground">Search to find organisations.</p>
            ) : (
              orgs.map((o) => (
                <label
                  key={o.id}
                  className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-surface-muted/50"
                >
                  <input
                    type="checkbox"
                    checked={selectedOrgIds.includes(o.id)}
                    onChange={() => toggleOrg(o.id)}
                    className="h-4 w-4"
                  />
                  <span className="text-[13px]">
                    <strong className="font-semibold text-foreground">{o.name}</strong>
                    <span className="text-muted-foreground"> · {String(o.id || '').slice(0, 8)}</span>
                  </span>
                </label>
              ))
            )}
          </div>
          <Button
            size="sm"
            className="h-8"
            disabled={applying || selectedOrgIds.length === 0}
            onClick={() => void applyToOrgs()}
          >
            {applying ? 'Applying…' : `Apply to ${selectedOrgIds.length} org(s)`}
          </Button>
          {applyResult ? (
            <pre className="overflow-auto rounded-md border border-border bg-surface px-3 py-2 text-[12px] text-foreground">
              {JSON.stringify(applyResult, null, 2)}
            </pre>
          ) : null}
        </Panel>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="h-8" onClick={() => navigate('/marketing/promo-offers')}>
            Back to list
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => {
              setCreated(null)
              setDraft(emptyDraft)
              setSelectedOrgIds([])
              setApplyResult(null)
            }}
          >
            Create another
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="ds-scope mx-auto max-w-[720px] space-y-4">
      <div>
        <div className="mb-1.5 text-xs text-muted-foreground">
          <Link to="/marketing/promo-offers" className="text-primary hover:underline">
            ← Promo offers
          </Link>
        </div>
        <h1 className="text-[15px] font-semibold leading-tight text-foreground">New promo</h1>
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
          Pick a service, free usage or discount, then who can redeem it.
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <form onSubmit={onSubmit}>
        <Panel title="Promo details" subtitle={`Preview: ${previewLine}`} bodyClassName="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">1. Service</Label>
            <Select value={draft.service_kind} onValueChange={(v) => setField('service_kind', v)}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SERVICES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">2. Benefit</Label>
            <Select value={draft.benefit_kind} onValueChange={(v) => setField('benefit_kind', v)}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BENEFITS.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {draft.benefit_kind === 'free_usage' ? (
            <>
              {draft.service_kind === 'voxbulk' ? (
                <>
                  <div className="space-y-1.5">
                    <Label className="text-[11px] text-muted-foreground">Plan</Label>
                    <PlanPickerSelect
                      plans={corePlans}
                      value={draft.plan_code}
                      onChange={(code) => setField('plan_code', code)}
                      className={planPickerClass}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-[11px] text-muted-foreground">Trial days</Label>
                    <Input
                      className="h-8"
                      type="number"
                      min={1}
                      value={draft.trial_days}
                      onChange={(e) => setField('trial_days', e.target.value)}
                    />
                  </div>
                </>
              ) : (
                <div className="space-y-1.5">
                  <Label className="text-[11px] text-muted-foreground">{usageLabel(draft.service_kind)}</Label>
                  <Input
                    className="h-8"
                    type="number"
                    min={1}
                    value={draft.usage_amount}
                    onChange={(e) => setField('usage_amount', e.target.value)}
                  />
                </div>
              )}
            </>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label className="text-[11px] text-muted-foreground">Discount type</Label>
                <Select value={draft.discount_type} onValueChange={(v) => setField('discount_type', v)}>
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">Percent off</SelectItem>
                    <SelectItem value="fixed_minor">Fixed £ off</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[11px] text-muted-foreground">
                  {draft.discount_type === 'percent' ? 'Percent (1–100)' : 'Pounds (£)'}
                </Label>
                <Input
                  className="h-8"
                  type="number"
                  min={1}
                  step={draft.discount_type === 'percent' ? 1 : 0.01}
                  value={draft.discount_value}
                  onChange={(e) => setField('discount_value', e.target.value)}
                />
              </div>
            </>
          )}

          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">3. Who can redeem</Label>
            <Select value={draft.redeem_mode} onValueChange={(v) => setField('redeem_mode', v)}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REDEEM_MODES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Max redemptions</Label>
              <Input
                className="h-8"
                type="number"
                min={1}
                value={draft.max_redemptions}
                onChange={(e) => setField('max_redemptions', e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Expires in (days)</Label>
              <Input
                className="h-8"
                type="number"
                min={1}
                value={draft.expires_in_days}
                onChange={(e) => setField('expires_in_days', e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Name</Label>
            <Input
              className="h-8"
              value={draft.name}
              onChange={(e) => setField('name', e.target.value)}
              placeholder="Display name for this promo code"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Code (optional)</Label>
            <Input
              className="h-8"
              value={draft.code}
              onChange={(e) => setField('code', e.target.value)}
              placeholder="Auto if blank"
            />
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <Button type="submit" size="sm" className="h-8" disabled={saving}>
              {saving ? 'Creating…' : 'Create promo'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => navigate('/marketing/promo-offers')}
            >
              Cancel
            </Button>
          </div>
        </Panel>
      </form>
    </div>
  )
}
