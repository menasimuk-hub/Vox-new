import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { leadSalesListUrl } from '../components/LeadSalesPipelineStrip'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { Modal } from '@/components/ui/Modal'
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

const TABS = [
  { key: 'all', label: 'All offers', icon: 'ti-ticket' },
  { key: 'active', label: 'Active', icon: 'ti-circle-check' },
  { key: 'expired', label: 'Expired / used', icon: 'ti-clock-off' },
  { key: 'sales', label: 'From lead sales', icon: 'ti-phone-call' },
]

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatShortDate(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function isExpired(row) {
  if (!row?.expires_at) return false
  return new Date(row.expires_at).getTime() < Date.now()
}

function isExhausted(row) {
  return Number(row?.redemption_count || 0) >= Number(row?.max_redemptions || 1)
}

function promoStatus(row) {
  if (!row?.is_active) return 'inactive'
  if (isExpired(row)) return 'expired'
  if (isExhausted(row)) return 'exhausted'
  return 'active'
}

function statusPillTone(status) {
  if (status === 'active') return 'success'
  if (status === 'inactive') return 'neutral'
  return 'warning'
}

function statusLabel(status) {
  if (status === 'active') return 'Active'
  if (status === 'inactive') return 'Inactive'
  if (status === 'expired') return 'Expired'
  return 'Fully redeemed'
}

function limitsLine(row) {
  if (row.benefit_summary) return row.benefit_summary
  if (row.offer_type === 'survey_credits') {
    return `${row.survey_contacts_included || 0} survey contacts`
  }
  if (row.offer_type === 'interview_credits') {
    return `${row.interview_contacts_included || 0} interviews`
  }
  const parts = []
  if (row.calls_included) parts.push(`${row.calls_included} calls`)
  if (row.whatsapp_included) parts.push(`${row.whatsapp_included} WhatsApp`)
  if (row.trial_days) parts.push(`${row.trial_days}-day trial`)
  return parts.join(' · ') || 'Plan defaults'
}

function offerTypeLabel(row) {
  if (row.benefit_summary) {
    const sk = row.service_kind || ''
    const bk = row.benefit_kind === 'discount' ? 'Discount' : 'Free'
    return `${bk} · ${sk || row.offer_type || 'promo'}`
  }
  if (row.offer_type === 'survey_credits') return 'Survey promo'
  if (row.offer_type === 'interview_credits') return 'Interview promo'
  return row.plan_code || 'Subscription'
}

export default function PromoOffers() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'all'
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState(
    params.get('created') ? 'Promo offer created.' : params.get('updated') ? 'Promo offer updated.' : '',
  )
  const [busyId, setBusyId] = useState('')
  const [query, setQuery] = useState('')
  const [applyPromo, setApplyPromo] = useState(null)
  const [orgQuery, setOrgQuery] = useState('')
  const [orgs, setOrgs] = useState([])
  const [selectedOrgIds, setSelectedOrgIds] = useState([])
  const [applying, setApplying] = useState(false)
  const [applyResult, setApplyResult] = useState(null)

  const load = useCallback(async () => {
    setError('')
    const data = await apiFetch('/admin/promo-offers')
    setRows(Array.isArray(data) ? data : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load promo offers')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const stats = useMemo(() => {
    const active = rows.filter((r) => promoStatus(r) === 'active')
    const sales = rows.filter((r) => r.lead_sales_task_id)
    const redeemed = rows.filter((r) => Number(r.redemption_count || 0) > 0)
    return {
      total: rows.length,
      active: active.length,
      sales: sales.length,
      redeemed: redeemed.length,
    }
  }, [rows])

  const tabCounts = useMemo(
    () => ({
      all: rows.length,
      active: rows.filter((r) => promoStatus(r) === 'active').length,
      expired: rows.filter((r) => ['expired', 'exhausted'].includes(promoStatus(r))).length,
      sales: rows.filter((r) => r.lead_sales_task_id).length,
    }),
    [rows],
  )

  const filtered = useMemo(() => {
    let list = rows
    if (tab === 'active') list = list.filter((r) => promoStatus(r) === 'active')
    if (tab === 'expired') list = list.filter((r) => ['expired', 'exhausted'].includes(promoStatus(r)))
    if (tab === 'sales') list = list.filter((r) => r.lead_sales_task_id)

    const q = query.trim().toLowerCase()
    if (!q) return list
    return list.filter((r) => {
      const hay = [
        r.code,
        r.name,
        r.plan_code,
        r.prospect_name,
        r.prospect_email,
        r.prospect_phone,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [rows, tab, query])

  const setTab = (next) => {
    const nextParams = new URLSearchParams(params)
    if (next === 'all') nextParams.delete('tab')
    else nextParams.set('tab', next)
    nextParams.delete('created')
    nextParams.delete('updated')
    setParams(nextParams)
  }

  const copyLink = async (row) => {
    const url = row.signup_url
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setMsg(`Copied signup link for ${row.code}.`)
    } catch {
      window.prompt('Copy signup link:', url)
    }
  }

  const copyCode = async (code) => {
    if (!code) return
    try {
      await navigator.clipboard.writeText(code)
      setMsg(`Copied promo code ${code}.`)
    } catch {
      window.prompt('Copy promo code:', code)
    }
  }

  const toggleActive = async (row) => {
    setBusyId(row.id)
    setMsg('')
    try {
      await apiFetch(`/admin/promo-offers/${row.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !row.is_active }),
      })
      await load()
      setMsg(row.is_active ? `Deactivated ${row.code}.` : `Activated ${row.code}.`)
    } catch (e) {
      setError(e?.message || 'Could not update promo')
    } finally {
      setBusyId('')
    }
  }

  const openApply = (row) => {
    setApplyPromo(row)
    setOrgQuery('')
    setOrgs([])
    setSelectedOrgIds([])
    setApplyResult(null)
    setError('')
  }

  const closeApply = () => {
    setApplyPromo(null)
    setOrgQuery('')
    setOrgs([])
    setSelectedOrgIds([])
    setApplyResult(null)
  }

  const searchOrgs = async () => {
    try {
      const data = await apiFetch(`/admin/organisations?search=${encodeURIComponent(orgQuery || '')}&limit=40`)
      setOrgs(Array.isArray(data) ? data : data?.items || data?.organisations || [])
    } catch (e) {
      setError(e?.message || 'Could not search organisations')
      setOrgs([])
    }
  }

  const toggleOrg = (id) => {
    setSelectedOrgIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const applyToSelectedOrgs = async () => {
    if (!applyPromo?.id || selectedOrgIds.length === 0) return
    setApplying(true)
    setApplyResult(null)
    setError('')
    try {
      const res = await apiFetch(`/admin/promo-offers/${applyPromo.id}/apply`, {
        method: 'POST',
        body: JSON.stringify({ org_ids: selectedOrgIds }),
      })
      setApplyResult(res)
      await load()
      const applied = Number(res?.applied || 0)
      const failed = Number(res?.failed || 0)
      setMsg(
        applied
          ? `Applied ${applyPromo.code} to ${applied} organisation(s)${failed ? ` · ${failed} skipped` : ''}.`
          : failed
            ? `No orgs applied (${failed} skipped — already redeemed or invalid).`
            : 'Apply finished.',
      )
    } catch (e) {
      setError(e?.message || 'Could not apply promo to organisations')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Promo offers</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            Create a code, then either share the signup link, let the customer enter it in Dashboard → Billing, or use{' '}
            <strong className="text-foreground">Apply to orgs</strong> / Org Control Center to assign it yourself to one or more organisations.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="h-8" onClick={() => load()} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/marketing/leads/tasks">Lead sales</Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/billing/products?tab=subscription">Subscription plans</Link>
          </Button>
          <Button size="sm" className="h-8" onClick={() => navigate('/marketing/promo-offers/new')}>
            New promo offer
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground">
          {msg}
        </div>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {TABS.map(({ key, label }) => (
            <TabsTrigger key={key} value={key}>
              {label} <span className="ml-1.5 text-muted-foreground">({tabCounts[key] ?? 0})</span>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-3.5 shadow-sm">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Total promos</div>
          <div className="mt-1.5 text-[20px] font-semibold text-foreground">{stats.total}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">Manual + lead sales offers</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-3.5 shadow-sm">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Active now</div>
          <div className="mt-1.5 text-[20px] font-semibold text-foreground">{stats.active}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">Valid code, not expired or used up</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-3.5 shadow-sm">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">From lead sales</div>
          <div className="mt-1.5 text-[20px] font-semibold text-foreground">{stats.sales}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">Auto-created on offer send</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-3.5 shadow-sm">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Redeemed</div>
          <div className="mt-1.5 text-[20px] font-semibold text-foreground">{stats.redeemed}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">At least one signup completed</div>
        </div>
      </div>

      <Panel
        title={
          tab === 'active'
            ? 'Active promo offers'
            : tab === 'expired'
              ? 'Expired or fully redeemed'
              : tab === 'sales'
                ? 'Lead sales promos'
                : 'All promo offers'
        }
        subtitle="Search by code, name, or prospect contact."
        action={
          <div className="flex items-center gap-2">
            <Input
              type="search"
              placeholder="Search code, name, prospect…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="h-8 w-64"
            />
            <Pill tone="info">{filtered.length} shown</Pill>
          </div>
        }
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Offer</TableHead>
              <TableHead>Benefit</TableHead>
              <TableHead>Uses</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && <TableLoading colSpan={6} />}
            {!loading && filtered.length === 0 && (
              <TableEmpty colSpan={6}>
                {query
                  ? 'No promos match your search.'
                  : tab === 'all'
                    ? 'No promo offers yet.'
                    : 'No promos in this view.'}
                {!query && tab === 'all' ? (
                  <Button size="sm" className="mt-3" onClick={() => navigate('/marketing/promo-offers/new')}>
                    Create promo offer
                  </Button>
                ) : null}
              </TableEmpty>
            )}
            {filtered.map((row) => {
              const status = promoStatus(row)
              const busy = busyId === row.id
              const prospectLine = [row.prospect_name, row.prospect_email || row.prospect_phone]
                .filter(Boolean)
                .join(' · ')
              return (
                <TableRow key={row.id}>
                  <TableCell>
                    <div className="flex items-start gap-2.5">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-surface-muted/40">
                        <i className="ti ti-ticket text-[16px] text-muted-foreground" />
                      </div>
                      <div className="min-w-0">
                        <Link
                          to={`/marketing/promo-offers/${row.id}/edit`}
                          className="text-[13px] font-semibold leading-tight text-foreground hover:underline"
                        >
                          {row.name || row.code}
                        </Link>
                        <button
                          type="button"
                          className="ml-2 inline-flex items-center gap-1 rounded border border-border bg-surface-muted/40 px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
                          onClick={() => copyCode(row.code)}
                          title="Copy code"
                        >
                          <i className="ti ti-copy text-[10px]" />
                          <span>{row.code}</span>
                        </button>
                        <div className="mt-0.5 text-[11px] text-muted-foreground">
                          {row.lead_sales_task_id ? 'Lead sales' : 'Manual'}
                          {row.created_at ? ` · ${formatShortDate(row.created_at)}` : ''}
                          {prospectLine ? ` · ${prospectLine}` : ''}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="text-[12.5px] font-semibold text-foreground">{offerTypeLabel(row)}</div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground" title={limitsLine(row)}>
                      {limitsLine(row)}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="font-semibold text-foreground">{row.redemption_count}</span>
                    <span className="text-muted-foreground"> / {row.max_redemptions}</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground" title={formatWhen(row.expires_at)}>
                    {formatShortDate(row.expires_at)}
                  </TableCell>
                  <TableCell>
                    <Pill tone={statusPillTone(status)}>{statusLabel(status)}</Pill>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button asChild size="sm" variant="ghost" className="h-7 w-7 p-0" title="Edit promo">
                        <Link to={`/marketing/promo-offers/${row.id}/edit`}>
                          <i className="ti ti-pencil text-[14px]" />
                        </Link>
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0"
                        onClick={() => openApply(row)}
                        disabled={!row.is_active}
                        title="Apply to organisations"
                      >
                        <i className="ti ti-building-community text-[14px]" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0"
                        onClick={() => copyLink(row)}
                        disabled={!row.signup_url}
                        title="Copy signup link"
                      >
                        <i className="ti ti-link text-[14px]" />
                      </Button>
                      {row.lead_sales_task_id ? (
                        <Button asChild size="sm" variant="ghost" className="h-7 w-7 p-0" title="Open lead sales task">
                          <Link to={leadSalesListUrl(row.lead_sales_task_id)}>
                            <i className="ti ti-phone-call text-[14px]" />
                          </Link>
                        </Button>
                      ) : null}
                      <Button
                        size="sm"
                        variant={row.is_active ? 'destructive' : 'ghost'}
                        className="h-7 w-7 p-0"
                        disabled={busy}
                        onClick={() => toggleActive(row)}
                        title={row.is_active ? 'Deactivate' : 'Activate'}
                      >
                        <i
                          className={`ti ${busy ? 'ti-loader-2' : row.is_active ? 'ti-player-pause' : 'ti-player-play'} text-[14px]`}
                        />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </StripeTable>
      </Panel>

      <Modal
        open={!!applyPromo}
        onOpenChange={(open) => !open && closeApply()}
        title={applyPromo ? `Apply ${applyPromo.code} to organisations` : 'Apply promo'}
        description={
          applyPromo
            ? `${applyPromo.benefit_summary || applyPromo.name || applyPromo.code}. Search, tick one or more orgs, then apply. Already-redeemed orgs are skipped.`
            : undefined
        }
        footer={
          <>
            <Button variant="outline" onClick={closeApply}>
              Close
            </Button>
            <Button disabled={applying || selectedOrgIds.length === 0} onClick={() => void applyToSelectedOrgs()}>
              {applying ? 'Applying…' : `Apply to ${selectedOrgIds.length || 0} org(s)`}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="flex gap-2">
            <Input
              placeholder="Search organisation name…"
              value={orgQuery}
              onChange={(e) => setOrgQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void searchOrgs()
                }
              }}
              className="flex-1"
            />
            <Button variant="outline" onClick={() => void searchOrgs()}>
              Search
            </Button>
          </div>
          <div className="max-h-64 overflow-auto rounded-md border border-border bg-surface-muted/30 p-2">
            {orgs.length === 0 ? (
              <p className="p-2 text-[13px] text-muted-foreground">Search to find organisations.</p>
            ) : (
              orgs.map((o) => (
                <label key={o.id} className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-surface-muted/50">
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
          {applyResult ? (
            <div className="rounded-md border border-border bg-surface px-3 py-2 text-[12px] text-foreground">
              Applied {applyResult.applied ?? 0} · failed/skipped {applyResult.failed ?? 0}
            </div>
          ) : null}
        </div>
      </Modal>
    </div>
  )
}
