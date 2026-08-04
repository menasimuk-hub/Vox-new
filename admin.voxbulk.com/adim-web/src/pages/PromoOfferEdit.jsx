import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'

const REDEEM_MODES = [
  { value: 'anyone', label: 'Anyone with the code (signup or Dashboard)' },
  { value: 'signup_only', label: 'Signup only' },
  { value: 'admin_only', label: 'Admin apply only' },
]

function daysUntil(expiresAt) {
  if (!expiresAt) return 30
  const end = new Date(expiresAt).getTime()
  if (Number.isNaN(end)) return 30
  const days = Math.ceil((end - Date.now()) / (24 * 60 * 60 * 1000))
  return Math.max(1, days)
}

export default function PromoOfferEdit() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [promo, setPromo] = useState(null)
  const [draft, setDraft] = useState({
    name: '',
    max_redemptions: 1,
    expires_in_days: 30,
    redeem_mode: 'anyone',
    is_active: true,
  })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const data = await apiFetch(`/admin/promo-offers/${id}`)
        if (cancelled) return
        setPromo(data)
        setDraft({
          name: data?.name || data?.code || '',
          max_redemptions: Number(data?.max_redemptions || 1),
          expires_in_days: daysUntil(data?.expires_at),
          redeem_mode: data?.redeem_mode || 'anyone',
          is_active: Boolean(data?.is_active),
        })
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load promo offer')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [id])

  const setField = (key, value) => setDraft((d) => ({ ...d, [key]: value }))

  const summary = useMemo(() => {
    if (!promo) return ''
    return promo.benefit_summary || promo.offer_type || ''
  }, [promo])

  const onSubmit = async (e) => {
    e.preventDefault()
    const name = String(draft.name || '').trim()
    if (!name) {
      setError('Name is required')
      return
    }
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/admin/promo-offers/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name,
          max_redemptions: Number(draft.max_redemptions) || 1,
          expires_in_days: Number(draft.expires_in_days) || 30,
          redeem_mode: draft.redeem_mode,
          is_active: Boolean(draft.is_active),
        }),
      })
      navigate('/marketing/promo-offers?updated=1')
    } catch (err) {
      setError(err?.message || 'Could not save promo offer')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="ds-scope mx-auto max-w-[720px] space-y-4">
        <p className="text-sm text-muted-foreground">Loading promo…</p>
      </div>
    )
  }

  if (!promo) {
    return (
      <div className="ds-scope mx-auto max-w-[720px] space-y-4">
        <div className="mb-1.5 text-xs text-muted-foreground">
          <Link to="/marketing/promo-offers" className="text-primary hover:underline">
            ← Promo offers
          </Link>
        </div>
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error || 'Promo not found'}
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
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Edit promo</h1>
          <Pill tone={draft.is_active ? 'success' : 'neutral'}>{draft.is_active ? 'Active' : 'Inactive'}</Pill>
        </div>
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
          Code <strong className="text-foreground">{promo.code}</strong>
          {summary ? ` · ${summary}` : ''}
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <form onSubmit={onSubmit}>
        <Panel title="Promo settings" bodyClassName="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Name</Label>
            <Input
              className="h-8"
              value={draft.name}
              onChange={(e) => setField('name', e.target.value)}
              placeholder="Display name for this promo code"
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Who can redeem</Label>
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
              <p className="text-[11px] text-muted-foreground">Already used: {promo.redemption_count || 0}</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Expires in (days from now)</Label>
              <Input
                className="h-8"
                type="number"
                min={1}
                value={draft.expires_in_days}
                onChange={(e) => setField('expires_in_days', e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="promo-active"
              checked={Boolean(draft.is_active)}
              onCheckedChange={(v) => setField('is_active', v)}
            />
            <Label htmlFor="promo-active" className="cursor-pointer text-[13px] text-foreground">
              Active
            </Label>
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <Button type="submit" size="sm" className="h-8" disabled={saving}>
              {saving ? 'Saving…' : 'Save changes'}
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
