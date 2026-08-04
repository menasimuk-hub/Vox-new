import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

const LAWFUL_BASES = ['consent', 'contract', 'legitimate_interests', 'legal_obligation']
const ARTICLE9 = [
  'explicit_consent',
  'employment_safeguard',
  'vital_interests',
  'legal_claims',
  'substantial_public_interest',
  'health_social_care',
  'public_health',
  'archiving_research',
]

const selectClass =
  'flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-[12px] shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

export default function ComplianceSettings() {
  const [orgs, setOrgs] = useState([])
  const [orgId, setOrgId] = useState('')
  const [defaults, setDefaults] = useState(null)
  const [audit, setAudit] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const loadOrgs = useCallback(async () => {
    const data = await apiFetch('/admin/organisations?limit=200')
    const list = Array.isArray(data?.items) ? data.items : []
    setOrgs(list)
    setOrgId((prev) => prev || String(list[0]?.id || ''))
  }, [])

  const loadOrg = useCallback(async (id) => {
    if (!id) return
    const data = await apiFetch(`/admin/compliance/organisations/${encodeURIComponent(id)}`)
    setDefaults(data?.defaults || {})
  }, [])

  const loadAudit = useCallback(async () => {
    const data = await apiFetch('/admin/compliance/audit?limit=50')
    setAudit(Array.isArray(data?.events) ? data.events : [])
  }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    Promise.all([loadOrgs(), loadAudit()])
      .catch((e) => setError(e?.message || 'Could not load compliance data'))
      .finally(() => setLoading(false))
  }, [loadOrgs, loadAudit])

  useEffect(() => {
    if (!orgId) return
    loadOrg(orgId).catch((e) => setError(e?.message || 'Could not load org defaults'))
  }, [orgId, loadOrg])

  const updateField = (key, value) => {
    setDefaults((prev) => ({ ...(prev || {}), [key]: value }))
  }

  const save = async (e) => {
    e.preventDefault()
    if (!orgId) return
    setSaving(true)
    setError('')
    setMsg('')
    try {
      await apiFetch(`/admin/compliance/organisations/${encodeURIComponent(orgId)}`, {
        method: 'PUT',
        body: JSON.stringify(defaults || {}),
      })
      setMsg('Organisation compliance defaults saved.')
      await loadAudit()
    } catch (err) {
      setError(err?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const runRetention = async () => {
    setError('')
    setMsg('')
    try {
      const data = await apiFetch('/admin/compliance/retention/run?dry_run=true', { method: 'POST' })
      setMsg(`Retention dry-run: ${JSON.stringify(data?.stats || {})}`)
    } catch (err) {
      setError(err?.message || 'Retention run failed')
    }
  }

  const selectedOrg = orgs.find((o) => o.id === orgId)

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <div className='mb-1.5 text-[12px] text-muted-foreground'>Compliance / UK baseline</div>
          <h1>UK compliance settings</h1>
          <p>
            PECR, UK GDPR, and DPA 2018 baseline. Configure org defaults; service orders inherit these unless
            overridden in order config. Survey WA and interview WA remain separate workflows — both use org
            suppression and STOP handling.
          </p>
        </div>
        <div className='actions'>
          <Button asChild variant='outline' size='sm' className='h-8'>
            <Link to='/compliance/audit'>Audit log</Link>
          </Button>
          <Button type='button' variant='outline' size='sm' className='h-8' onClick={runRetention}>
            Retention dry-run
          </Button>
        </div>
      </div>

      {error ? (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          <strong>{error}</strong>
        </div>
      ) : null}
      {msg ? (
        <div className='rounded-md border border-border bg-success-soft px-3 py-2 text-sm text-success'>
          <strong>{msg}</strong>
        </div>
      ) : null}

      <Panel title='Organisation defaults' subtitle='Inherited by service orders unless overridden.'>
        {loading ? (
          <p className='text-sm text-muted-foreground'>Loading…</p>
        ) : (
          <form onSubmit={save} className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Organisation</Label>
              <select className={selectClass} value={orgId} onChange={(e) => setOrgId(e.target.value)}>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name || o.id}
                  </option>
                ))}
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Default lawful basis</Label>
              <select
                className={selectClass}
                value={defaults?.lawful_basis_default || ''}
                onChange={(e) => updateField('lawful_basis_default', e.target.value)}
              >
                <option value=''>—</option>
                {LAWFUL_BASES.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Privacy notice URL</Label>
              <Input
                className='h-8'
                value={defaults?.privacy_notice_url || ''}
                onChange={(e) => updateField('privacy_notice_url', e.target.value)}
                placeholder='https://…'
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Contact email</Label>
              <Input
                className='h-8'
                value={defaults?.contact_email || ''}
                onChange={(e) => updateField('contact_email', e.target.value)}
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>DPO / data protection email</Label>
              <Input
                className='h-8'
                value={defaults?.dpo_email || ''}
                onChange={(e) => updateField('dpo_email', e.target.value)}
              />
            </div>
            <label className='flex cursor-pointer items-center gap-2.5 self-end pb-1 text-sm text-muted-foreground'>
              <input
                type='checkbox'
                checked={Boolean(defaults?.opt_out_enabled ?? true)}
                onChange={(e) => updateField('opt_out_enabled', e.target.checked)}
              />
              Opt-out enabled (PECR)
            </label>
            <label className='flex cursor-pointer items-center gap-2.5 self-end pb-1 text-sm text-muted-foreground'>
              <input
                type='checkbox'
                checked={Boolean(defaults?.special_category_data_present_default)}
                onChange={(e) => updateField('special_category_data_present_default', e.target.checked)}
              />
              Special category data (default)
            </label>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Article 9 condition (if special category)</Label>
              <select
                className={selectClass}
                value={defaults?.article9_condition_default || ''}
                onChange={(e) => updateField('article9_condition_default', e.target.value || null)}
              >
                <option value=''>—</option>
                {ARTICLE9.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </div>
            <div className='space-y-1 sm:col-span-2'>
              <Label className='text-[12px]'>Just-in-time privacy intro (default)</Label>
              <Input
                className='h-8'
                value={defaults?.privacy_intro_text_default || ''}
                onChange={(e) => updateField('privacy_intro_text_default', e.target.value)}
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Retention: messages (days)</Label>
              <Input
                className='h-8'
                type='number'
                min={1}
                value={defaults?.retention_days_messages ?? 365}
                onChange={(e) => updateField('retention_days_messages', Number(e.target.value))}
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Retention: responses (days)</Label>
              <Input
                className='h-8'
                type='number'
                min={1}
                value={defaults?.retention_days_responses ?? 730}
                onChange={(e) => updateField('retention_days_responses', Number(e.target.value))}
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Retention: recordings (days)</Label>
              <Input
                className='h-8'
                type='number'
                min={1}
                value={defaults?.retention_days_recordings ?? 90}
                onChange={(e) => updateField('retention_days_recordings', Number(e.target.value))}
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Retention: transcripts (days)</Label>
              <Input
                className='h-8'
                type='number'
                min={1}
                value={defaults?.retention_days_transcripts ?? 365}
                onChange={(e) => updateField('retention_days_transcripts', Number(e.target.value))}
              />
            </div>
            {selectedOrg ? (
              <p className='text-sm text-muted-foreground sm:col-span-2'>
                Orders for {selectedOrg.name} must pass compliance checks before launch/send. Override per order via
                API <code>PUT /admin/compliance/orders/:id</code> with a <code>compliance</code> object.
              </p>
            ) : null}
            <div className='sm:col-span-2'>
              <Button type='submit' size='sm' className='h-8' disabled={saving}>
                {saving ? 'Saving…' : 'Save org defaults'}
              </Button>
            </div>
          </form>
        )}
      </Panel>

      <Panel title='Recent compliance audit' bodyClassName='overflow-x-auto'>
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Event</TableHead>
              <TableHead>Org</TableHead>
              <TableHead>Order</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {audit.length === 0 ? (
              <TableEmpty colSpan={4}>No audit events.</TableEmpty>
            ) : (
              audit.map((ev) => (
                <TableRow key={ev.id}>
                  <TableCell>{ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}</TableCell>
                  <TableCell>
                    <code className='text-[11px]'>{ev.event_type}</code>
                  </TableCell>
                  <TableCell className='text-muted-foreground'>
                    {ev.org_id ? ev.org_id.slice(0, 8) : '—'}
                  </TableCell>
                  <TableCell className='text-muted-foreground'>
                    {ev.order_id ? ev.order_id.slice(0, 8) : '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
