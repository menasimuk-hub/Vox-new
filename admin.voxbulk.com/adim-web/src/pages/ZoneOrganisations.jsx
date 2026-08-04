import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { orgStatusPill, subscriptionLabel, zoneFromParam, ZONE_CONFIG } from '../lib/marketZone'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
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

const STATUS_PILL_TONE = {
  'p-green': 'success',
  'p-amber': 'warning',
  'p-red': 'danger',
  'p-cyan': 'info',
}

export default function ZoneOrganisations() {
  const { zone: zoneParam } = useParams()
  const zone = zoneFromParam(zoneParam)
  const navigate = useNavigate()
  const config = zone ? ZONE_CONFIG[zone] : null

  const [items, setItems] = useState(null)
  const [listError, setListError] = useState('')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const title = useMemo(() => (config ? config.title : 'Zone'), [config])

  useEffect(() => {
    if (!zone) return
    let cancelled = false
    setListError('')
    setBusy(true)
    ;(async () => {
      try {
        const qs = new URLSearchParams()
        if (search.trim()) qs.set('search', search.trim())
        qs.set('zone', zone)
        qs.set('limit', '200')
        const data = await apiFetch(`/admin/organisations?${qs.toString()}`)
        if (!cancelled) setItems(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) {
          setItems([])
          setListError(e?.message || 'Could not load organisations')
        }
      } finally {
        if (!cancelled) setBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [zone, search, refreshKey])

  if (!zone || !config) {
    return (
      <div className="ds-scope rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        Unknown zone. Choose GB, USA, Canada, or Australia from the sidebar.
      </div>
    )
  }

  return (
    <div className="ds-scope space-y-4">
      {listError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {listError}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">
            {config.flag} {config.label}
          </h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Organisations registered in {title}. Tax, agents, and pricing follow this market zone.
          </p>
        </div>
        <div className="ml-auto">
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            disabled={busy}
            onClick={() => setRefreshKey((k) => k + 1)}
          >
            Refresh
          </Button>
        </div>
      </div>

      <Panel
        title={`${title} organisations`}
        subtitle="Search, review status, and open organisation ops."
        action={<Pill tone="info">{items ? `${items.length}` : '—'}</Pill>}
        bodyClassName="space-y-3"
      >
        <Input
          placeholder={`Search ${title} organisations…`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 max-w-sm"
        />
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Organisation</TableHead>
              <TableHead>Users</TableHead>
              <TableHead>Subscription</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Wallet</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(items || []).map((o) => {
              const pill = orgStatusPill(o)
              return (
                <TableRow key={o.id}>
                  <TableCell>
                    <div className="flex flex-col leading-tight">
                      <strong className="font-medium">{o.name}</strong>
                      <span className="text-[11px] text-muted-foreground">
                        {o.city || o.country
                          ? `${o.city || ''}${o.city && o.country ? ', ' : ''}${o.country || ''}`
                          : o.contact_email || '—'}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{o.user_count ?? 0}</TableCell>
                  <TableCell>
                    <div className="flex flex-col leading-tight">
                      <span>{o.plan_name || o.plan_code || '—'}</span>
                      <span className="text-[11px] text-muted-foreground">
                        {subscriptionLabel(o.subscription_status)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Pill tone={STATUS_PILL_TONE[pill.cls] || 'neutral'}>{pill.text}</Pill>
                  </TableCell>
                  <TableCell>{o.wallet_balance_display || '—'}</TableCell>
                  <TableCell>
                    <div className="flex justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7"
                        onClick={() => {
                          localStorage.setItem('voxbulk_admin_selected_org_id', o.id)
                          navigate(`/organisations/${encodeURIComponent(o.id)}`)
                        }}
                      >
                        Edit
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
            {!items && <TableLoading colSpan={6} />}
            {items && items.length === 0 && (
              <TableEmpty colSpan={6}>No organisations in this zone yet.</TableEmpty>
            )}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
