import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { orgStatusPill, subscriptionLabel } from '../lib/marketZone'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { KpiCard } from '@/components/ui/KpiCard'
import { Progress } from '@/components/ui/Progress'
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

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function UsageMeter({ label, used, included, percent }) {
  const pct = Math.min(100, Number(percent || 0))
  return (
    <div className="space-y-1 rounded-lg border border-border bg-surface-muted/50 p-2.5">
      <div className="flex items-center justify-between text-[12px]">
        <span className="font-medium text-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {used ?? 0} / {included ?? 0}
        </span>
      </div>
      <Progress value={pct} className="h-1" />
    </div>
  )
}

const STATUS_PILL_TONE = {
  'p-green': 'success',
  'p-amber': 'warning',
  'p-red': 'danger',
  'p-cyan': 'info',
}

export default function OrganisationDetail() {
  const { orgId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [walletAmount, setWalletAmount] = useState('50')
  const [walletNote, setWalletNote] = useState('')
  const [walletBusy, setWalletBusy] = useState(false)

  const org = data?.organisation
  const pill = useMemo(() => orgStatusPill(org), [org])

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoadError('')
    setBusy(true)
    try {
      const res = await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/operations`)
      setData(res)
    } catch (e) {
      setLoadError(e?.message || 'Could not load organisation')
      setData(null)
    } finally {
      setBusy(false)
    }
  }, [orgId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const creditWallet = async () => {
    const gbp = Number(walletAmount)
    if (!Number.isFinite(gbp) || gbp <= 0) {
      window.alert('Enter a positive amount')
      return
    }
    setWalletBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/wallet/credit`, {
        method: 'POST',
        body: JSON.stringify({
          amount_pence: Math.round(gbp * 100),
          note: walletNote.trim() || undefined,
        }),
      })
      setWalletNote('')
      await refresh()
    } catch (e) {
      window.alert(e?.message || 'Wallet top-up failed')
    } finally {
      setWalletBusy(false)
    }
  }

  const openProfile = () => {
    localStorage.setItem('voxbulk_admin_selected_org_id', orgId)
    navigate('/organisations/profile')
  }

  if (!orgId) {
    return (
      <div className="ds-scope rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        Missing organisation id.
      </div>
    )
  }

  return (
    <div className="ds-scope space-y-4">
      {loadError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {loadError}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <div className="mb-1 text-[11px] text-muted-foreground">
            <Link to="/organisations" className="hover:underline">
              Organisations
            </Link>
            {org?.market_zone ? (
              <>
                {' '}
                /{' '}
                <Link to={`/organisations/zone/${org.market_zone}`} className="hover:underline">
                  {org.market_label || org.market_zone}
                </Link>
              </>
            ) : null}{' '}
            / {org?.name || '…'}
          </div>
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">
            {org?.name || 'Organisation'}
          </h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            {org?.market_label || '—'}
            {org?.city || org?.country ? ` · ${[org.city, org.country].filter(Boolean).join(', ')}` : ''}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="h-8" disabled={busy} onClick={refresh}>
            {busy ? 'Loading…' : 'Refresh'}
          </Button>
          <Button variant="outline" size="sm" className="h-8" onClick={openProfile}>
            Full profile
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <KpiCard label="Users" value={org?.user_count ?? '—'} index={0} />
        <KpiCard
          label={subscriptionLabel(org?.subscription_status)}
          value={org?.plan_name || org?.plan_code || '—'}
          tone="info"
          index={1}
        />
        <div className="rounded-lg border border-border bg-card p-3.5 shadow-sm">
          <div className="mt-1">
            <Pill tone={STATUS_PILL_TONE[pill.cls] || 'neutral'}>{pill.text}</Pill>
          </div>
          <div className="mt-2 text-[11px] text-muted-foreground">Account status</div>
        </div>
        <KpiCard label="Wallet balance" value={org?.wallet_balance_display || '—'} tone="success" index={3} />
      </div>

      <Panel
        title="Finance summary"
        subtitle="Plan, next charge, and cancellation."
        action={
          data?.subscription_finance?.cancel_at_period_end ? (
            <Pill tone="warning">Cancel at period end</Pill>
          ) : null
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Plan', org?.plan_name || org?.plan_code || '—'],
            [
              'Next billing',
              data?.subscription_finance?.next_billing_date
                ? fmtWhen(data.subscription_finance.next_billing_date)
                : '—',
            ],
            ['Next charge', data?.subscription_finance?.amount_next_payment_display || '—'],
            [
              'Cancellation',
              data?.cancellation_preview?.status || data?.subscription_finance?.cancellation_status || 'none',
            ],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-border bg-surface-muted/40 p-2.5">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
              <div className="mt-0.5 text-[13px] font-medium text-foreground">{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={openProfile}>
            Full profile (plan)
          </Button>
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link
              to="/organisations/all-users"
              onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', orgId)}
            >
              Finance console
            </Link>
          </Button>
        </div>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Contact & billing" subtitle="Primary contact on the organisation.">
          <div className="grid gap-2 sm:grid-cols-2">
            {[
              ['Contact', org?.contact_name || '—'],
              ['Email', org?.contact_email || '—'],
              ['Phone', org?.contact_phone || '—'],
              ['Created', fmtWhen(org?.created_at)],
              ['Branches', org?.branch_count ?? 0],
            ].map(([label, value]) => (
              <div key={label}>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
                <div className="text-[13px] text-foreground">{value}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Top up wallet" subtitle={`Credit prepaid wallet (${org?.currency_symbol || '£'} as GBP pence).`}>
          <div className="mb-3 flex flex-wrap gap-2">
            <Input
              type="number"
              min="0"
              step="0.01"
              value={walletAmount}
              onChange={(e) => setWalletAmount(e.target.value)}
              placeholder="Amount"
              className="h-8 w-32"
            />
            <Input
              value={walletNote}
              onChange={(e) => setWalletNote(e.target.value)}
              placeholder="Note (optional)"
              className="h-8 min-w-[180px] flex-1"
            />
          </div>
          <Button type="button" size="sm" className="h-8" disabled={walletBusy} onClick={creditWallet}>
            {walletBusy ? 'Crediting…' : 'Credit wallet'}
          </Button>
        </Panel>
      </div>

      <Panel
        title="Usage this period"
        subtitle={
          data?.usage?.period_start
            ? `${fmtWhen(data.usage.period_start)} → ${fmtWhen(data.usage.period_end)}`
            : 'Current billing period meters.'
        }
      >
        {!data?.usage ? (
          <p className="text-[12px] text-muted-foreground">No usage record for the current billing period.</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <UsageMeter label="Calls" {...data.usage.calls} />
            <UsageMeter label="WhatsApp" {...data.usage.whatsapp} />
            <UsageMeter label="SMS" {...data.usage.sms} />
            <div className="space-y-1 rounded-lg border border-border bg-surface-muted/50 p-2.5">
              <div className="flex items-center justify-between text-[12px]">
                <span className="font-medium text-foreground">Pack credits</span>
                <span className="tabular-nums text-muted-foreground">
                  {data.usage.pack_credits?.used ?? 0} / {data.usage.pack_credits?.included ?? 0}
                </span>
              </div>
            </div>
            {data.usage.estimated_overage_gbp != null ? (
              <p className="col-span-full text-[12px] text-muted-foreground">
                Estimated overage: {org?.currency_symbol || '£'}
                {Number(data.usage.estimated_overage_gbp).toFixed(2)}
              </p>
            ) : null}
          </div>
        )}
      </Panel>

      <Panel
        title="Running tasks"
        subtitle="Draft and in-progress service orders."
        action={<Pill tone="info">{data?.running_orders?.length ?? 0}</Pill>}
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Service</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Payment</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!data && <TableLoading colSpan={5} />}
            {data &&
              (data.running_orders || []).map((o) => (
                <TableRow key={o.id}>
                  <TableCell>{o.service_code || '—'}</TableCell>
                  <TableCell>{o.title || o.id}</TableCell>
                  <TableCell>{o.status || '—'}</TableCell>
                  <TableCell>{o.payment_status || '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{fmtWhen(o.updated_at || o.created_at)}</TableCell>
                </TableRow>
              ))}
            {data && (!data.running_orders || data.running_orders.length === 0) && (
              <TableEmpty colSpan={5}>No running or draft tasks.</TableEmpty>
            )}
          </TableBody>
        </StripeTable>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Users" action={<Pill tone="info">{data?.users?.length ?? 0}</Pill>}>
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!data && <TableLoading colSpan={3} />}
              {data &&
                (data.users || []).map((u) => (
                  <TableRow key={u.user_id}>
                    <TableCell>{u.email}</TableCell>
                    <TableCell>{u.role || '—'}</TableCell>
                    <TableCell>{u.is_active ? 'Active' : 'Blocked'}</TableCell>
                  </TableRow>
                ))}
              {data && (!data.users || data.users.length === 0) && (
                <TableEmpty colSpan={3}>No users linked.</TableEmpty>
              )}
            </TableBody>
          </StripeTable>
        </Panel>

        <Panel title="Invoices" action={<Pill tone="info">{data?.invoices?.length ?? 0}</Pill>}>
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Number</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Total</TableHead>
                <TableHead>Date</TableHead>
                <TableHead className="text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {!data && <TableLoading colSpan={5} />}
              {data &&
                (data.invoices || []).map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell>{inv.invoice_number || inv.id}</TableCell>
                    <TableCell>{inv.status || '—'}</TableCell>
                    <TableCell>{inv.total_display || inv.total_gbp || '—'}</TableCell>
                    <TableCell className="text-muted-foreground">{fmtWhen(inv.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end">
                        <Button asChild size="sm" variant="outline" className="h-7">
                          <Link
                            to="/organisations/all-users"
                            onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', orgId)}
                          >
                            In OCC
                          </Link>
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              {data && (!data.invoices || data.invoices.length === 0) && (
                <TableEmpty colSpan={5}>No invoices yet.</TableEmpty>
              )}
            </TableBody>
          </StripeTable>
        </Panel>
      </div>

      {data?.recent_orders?.length > 0 ? (
        <Panel title="Recent service orders" subtitle="Latest orders for this organisation.">
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Service</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.recent_orders.map((o) => (
                <TableRow key={o.id}>
                  <TableCell>{o.service_code}</TableCell>
                  <TableCell>{o.title || o.id}</TableCell>
                  <TableCell>{o.status}</TableCell>
                  <TableCell className="text-muted-foreground">{fmtWhen(o.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : null}
    </div>
  )
}
