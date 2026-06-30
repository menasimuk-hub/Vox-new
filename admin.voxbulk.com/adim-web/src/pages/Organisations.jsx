import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { orgStatusPill, subscriptionLabel } from '../lib/marketZone'
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

export default function Organisations() {
  const navigate = useNavigate()
  const [items, setItems] = useState(null)
  const [listError, setListError] = useState('')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async (q) => {
    setListError('')
    let cancelled = false
    try {
      const qs = new URLSearchParams()
      if (q && String(q).trim()) qs.set('search', String(q).trim())
      qs.set('limit', '200')
      const data = await apiFetch(`/admin/organisations?${qs.toString()}`)
      if (!cancelled) setItems(Array.isArray(data) ? data : [])
    } catch (e) {
      if (!cancelled) {
        setItems([])
        setListError(e?.message || 'Could not load organisations')
      }
    }
    return () => {
      cancelled = true
    }
  }

  useEffect(() => {
    let cancelled = false
    setListError('')
    setBusy(true)
    ;(async () => {
      try {
        const qs = new URLSearchParams()
        if (search && search.trim()) qs.set('search', search.trim())
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
  }, [search])

  const createOrg = async () => {
    const name = window.prompt('Organisation / clinic name?')
    if (!name) return
    try {
      const created = await apiFetch('/admin/organisations', {
        method: 'POST',
        body: JSON.stringify({ name: String(name).trim() }),
      })
      localStorage.setItem('voxbulk_admin_selected_org_id', created.id)
      navigate(`/organisations/${encodeURIComponent(created.id)}`)
    } catch (e) {
      window.alert(e?.message || 'Could not create organisation')
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      {listError && (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          {listError}
        </div>
      )}
      <div className='pageTop'>
        <div>
          <h1>All organisations</h1>
          <p>Manage organisations, categories, contacts, and suspension state.</p>
        </div>
        <div className='actions'>
          <Button variant='outline' size='sm' className='h-8' onClick={() => load(search)} disabled={busy}>
            Refresh
          </Button>
          <Button size='sm' className='h-8' onClick={() => navigate('/onboarding/add-customer')}>
            Add customer
          </Button>
        </div>
      </div>

      <Panel
        title='Organisation list'
        subtitle='Search, review status, and jump into an organisation.'
        action={<Pill tone='info'>{items ? `${items.length}` : '—'}</Pill>}
        bodyClassName='space-y-3'
      >
        <Input
          placeholder='Search organisations…'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className='h-8 max-w-sm'
        />
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Organisation</TableHead>
              <TableHead>Zone</TableHead>
              <TableHead>Subscription</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Users</TableHead>
              <TableHead>Wallet</TableHead>
              <TableHead className='text-right'>Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(items || []).map((o) => {
              const pill = orgStatusPill(o)
              return (
                <TableRow key={o.id}>
                  <TableCell>
                    <div className='flex flex-col leading-tight'>
                      <strong className='font-medium'>{o.name}</strong>
                      <span className='text-[11px] text-muted-foreground'>
                        {o.city || o.country
                          ? `${o.city || ''}${o.city && o.country ? ', ' : ''}${o.country || ''}`
                          : '—'}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className='text-muted-foreground'>{o.market_label || '—'}</TableCell>
                  <TableCell>
                    <div className='flex flex-col leading-tight'>
                      <span>{o.plan_name || o.plan_code || '—'}</span>
                      <span className='text-[11px] text-muted-foreground'>
                        {subscriptionLabel(o.subscription_status)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Pill tone={STATUS_PILL_TONE[pill.cls] || 'neutral'}>{pill.text}</Pill>
                  </TableCell>
                  <TableCell className='text-muted-foreground'>{o.user_count} users</TableCell>
                  <TableCell>{o.wallet_balance_display || '—'}</TableCell>
                  <TableCell>
                    <div className='flex justify-end gap-1.5'>
                      <Button
                        variant='outline'
                        size='sm'
                        className='h-7'
                        onClick={() => {
                          localStorage.setItem('voxbulk_admin_selected_org_id', o.id)
                          navigate('/organisations/profile')
                        }}
                      >
                        Profile
                      </Button>
                      <Button
                        variant='outline'
                        size='sm'
                        className='h-7'
                        onClick={() => {
                          localStorage.setItem('voxbulk_admin_selected_org_id', o.id)
                          navigate(`/organisations/${encodeURIComponent(o.id)}`)
                        }}
                      >
                        Ops
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
            {!items && <TableLoading colSpan={7} />}
            {items && items.length === 0 && (
              <TableEmpty colSpan={7}>No organisations found.</TableEmpty>
            )}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
