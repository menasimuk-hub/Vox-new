import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Switch } from '@/components/ui/Switch'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

export default function PendingSignups() {
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [autoApprovePromo, setAutoApprovePromo] = useState(true)
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)

  async function loadSettings() {
    setSettingsLoading(true)
    try {
      const data = await apiFetch('/admin/onboarding/settings')
      setAutoApprovePromo(Boolean(data?.settings?.auto_approve_promo_signups ?? true))
    } catch {
      setAutoApprovePromo(true)
    } finally {
      setSettingsLoading(false)
    }
  }

  async function load() {
    try {
      const data = await apiFetch('/admin/onboarding/requests?status_filter=pending')
      setRows(Array.isArray(data) ? data : [])
    } catch {
      setRows([])
    }
  }

  useEffect(() => {
    loadSettings()
    load()
  }, [])

  const saveAutoApprove = async (next) => {
    setSettingsSaving(true)
    try {
      const data = await apiFetch('/admin/onboarding/settings', {
        method: 'PUT',
        body: JSON.stringify({ auto_approve_promo_signups: next }),
      })
      setAutoApprovePromo(Boolean(data?.settings?.auto_approve_promo_signups ?? next))
    } catch (e) {
      window.alert(e?.message || 'Could not save setting')
    } finally {
      setSettingsSaving(false)
    }
  }

  const decide = async (id, action) => {
    setBusyId(id)
    try {
      await apiFetch(`/admin/onboarding/requests/${id}/${action}`, { method: 'POST', body: JSON.stringify({}) })
      await load()
    } catch (e) {
      window.alert(e?.message || 'Action failed')
    } finally {
      setBusyId(null)
    }
  }

  const openOrgUsers = (organisationId) => {
    localStorage.setItem('voxbulk_admin_selected_org_id', organisationId)
    navigate('/organisations/profile?tab=users')
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Pending signups</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            Self-serve onboarding requests awaiting approval. <strong className="text-foreground">Approve</strong> activates the user so they can log in.
            <span className="text-muted-foreground"> Rejected users cannot log in.</span>
          </p>
        </div>
        <Button variant="outline" size="sm" className="h-8" onClick={load}>
          Refresh
        </Button>
      </div>

      <Panel
        title="Promo signup approval"
        subtitle="When enabled, customers who sign up with a sales promo link are activated immediately — no manual approval needed. Signups without a promo code always require manual approval."
      >
        <label className="flex items-center gap-3 cursor-pointer">
          <Switch
            checked={autoApprovePromo}
            disabled={settingsLoading || settingsSaving}
            onCheckedChange={(next) => {
              setAutoApprovePromo(next)
              saveAutoApprove(next)
            }}
            aria-label="Auto-approve promo signups"
          />
          <span className="text-[13px]">
            <strong className="font-semibold text-foreground">Auto-approve promo signups</strong>
            <span className="text-muted-foreground">
              {settingsLoading ? ' (loading…)' : settingsSaving ? ' (saving…)' : autoApprovePromo ? ' — on (default)' : ' — off (manual approval)'}
            </span>
          </span>
        </label>
      </Panel>

      <Panel title="Pending requests" subtitle="Self-serve signups awaiting manual review.">
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Organisation</TableHead>
              <TableHead>User</TableHead>
              <TableHead>Plan</TableHead>
              <TableHead>Promo</TableHead>
              <TableHead>Payment</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!rows && <TableLoading colSpan={8} />}
            {rows && rows.length === 0 && <TableEmpty colSpan={8}>No pending requests.</TableEmpty>}
            {(rows || []).map((r) => (
              <TableRow key={r.id}>
                <TableCell>{r.id}</TableCell>
                <TableCell>{r.org_name || r.org_id}</TableCell>
                <TableCell>{r.user_email || r.user_id}</TableCell>
                <TableCell>{r.plan_code}</TableCell>
                <TableCell>{r.promo_code || '—'}</TableCell>
                <TableCell>{r.payment_method}</TableCell>
                <TableCell className="text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => openOrgUsers(r.org_id)}>
                      Org users
                    </Button>
                    <Button type="button" variant="outline" size="sm" className="h-7" disabled={busyId === r.id} onClick={() => decide(r.id, 'approve')}>
                      Approve
                    </Button>
                    <Button type="button" variant="destructive" size="sm" className="h-7" disabled={busyId === r.id} onClick={() => decide(r.id, 'reject')}>
                      Reject
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
