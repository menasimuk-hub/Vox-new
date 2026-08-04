import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

const PAGE_SIZE = 20

const selectClass =
  'flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-[12px] shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

export default function ComplianceOptOuts() {
  const [orgs, setOrgs] = useState([])
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const [orgId, setOrgId] = useState('')
  const [phone, setPhone] = useState('')
  const [reason, setReason] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const [addOrgId, setAddOrgId] = useState('')
  const [addPhone, setAddPhone] = useState('')
  const [addName, setAddName] = useState('')
  const [addReason, setAddReason] = useState('Manual admin add')
  const [saving, setSaving] = useState(false)

  const loadOrgs = useCallback(async () => {
    const data = await apiFetch('/admin/organisations?limit=200')
    const list = Array.isArray(data?.items) ? data.items : []
    setOrgs(list)
    setAddOrgId((prev) => prev || String(list[0]?.id || ''))
  }, [])

  const loadList = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(PAGE_SIZE))
      if (orgId) params.set('org_id', orgId)
      if (phone.trim()) params.set('phone', phone.trim())
      if (reason.trim()) params.set('reason', reason.trim())
      if (fromDate) params.set('from_date', `${fromDate}T00:00:00`)
      if (toDate) params.set('to_date', `${toDate}T23:59:59`)
      const data = await apiFetch(`/admin/opt-outs?${params.toString()}`)
      setItems(Array.isArray(data?.items) ? data.items : [])
      setTotal(Number(data?.total) || 0)
      setPages(Number(data?.pages) || 1)
    } catch (e) {
      setError(e?.message || 'Could not load opt-out list')
    } finally {
      setLoading(false)
    }
  }, [page, orgId, phone, reason, fromDate, toDate])

  useEffect(() => {
    loadOrgs().catch((e) => setError(e?.message || 'Could not load organisations'))
  }, [loadOrgs])

  useEffect(() => {
    void loadList()
  }, [loadList])

  const onSearch = (e) => {
    e.preventDefault()
    setPage(1)
    void loadList()
  }

  const onAdd = async (e) => {
    e.preventDefault()
    if (!addOrgId || !addPhone.trim()) {
      setError('Organisation and phone are required')
      return
    }
    setSaving(true)
    setError('')
    setMsg('')
    try {
      await apiFetch('/admin/opt-outs', {
        method: 'POST',
        body: JSON.stringify({
          org_id: addOrgId,
          phone: addPhone.trim(),
          name: addName.trim() || undefined,
          reason: addReason.trim() || undefined,
        }),
      })
      setMsg('Number added to opt-out list')
      setAddPhone('')
      setAddName('')
      setPage(1)
      await loadList()
    } catch (err) {
      setError(err?.message || 'Could not add opt-out')
    } finally {
      setSaving(false)
    }
  }

  const onRemove = async (id) => {
    if (!window.confirm('Remove this number from the opt-out list?')) return
    setError('')
    try {
      await apiFetch(`/admin/opt-outs/${encodeURIComponent(id)}`, { method: 'DELETE' })
      setMsg('Removed from opt-out list')
      await loadList()
    } catch (err) {
      setError(err?.message || 'Could not remove opt-out')
    }
  }

  const fmtDate = (raw) => {
    if (!raw) return '—'
    try {
      return new Date(raw).toLocaleString()
    } catch {
      return String(raw)
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <div className='mb-1.5 text-[12px] text-muted-foreground'>
            <Link to='/compliance/consent' className='text-primary hover:underline'>
              Compliance
            </Link>{' '}
            / STOP opt-out list
          </div>
          <h1>STOP / opt-out list</h1>
          <p>Platform-wide numbers that must not be called or messaged (all organisations).</p>
        </div>
      </div>

      {error ? (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          {error}
        </div>
      ) : null}
      {msg ? (
        <div className='rounded-md border border-border bg-success-soft px-3 py-2 text-sm text-success'>{msg}</div>
      ) : null}

      <Panel title='Filters' subtitle='Search the platform opt-out list.'>
        <form onSubmit={onSearch} className='space-y-3'>
          <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5'>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Organisation</Label>
              <select
                className={selectClass}
                value={orgId}
                onChange={(e) => {
                  setOrgId(e.target.value)
                  setPage(1)
                }}
              >
                <option value=''>All organisations</option>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name || o.id}
                  </option>
                ))}
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Phone</Label>
              <Input className='h-8' placeholder='+4477…' value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Reason</Label>
              <Input
                className='h-8'
                placeholder='whatsapp_keyword…'
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>From</Label>
              <Input className='h-8' type='date' value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>To</Label>
              <Input className='h-8' type='date' value={toDate} onChange={(e) => setToDate(e.target.value)} />
            </div>
          </div>
          <div className='flex gap-2'>
            <Button type='submit' size='sm' className='h-8'>
              Search
            </Button>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='h-8'
              onClick={() => {
                setOrgId('')
                setPhone('')
                setReason('')
                setFromDate('')
                setToDate('')
                setPage(1)
              }}
            >
              Clear
            </Button>
          </div>
        </form>
      </Panel>

      <Panel title='Add number' subtitle='Manually suppress a phone across the platform.'>
        <form onSubmit={onAdd} className='space-y-3'>
          <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Organisation</Label>
              <select className={selectClass} value={addOrgId} onChange={(e) => setAddOrgId(e.target.value)} required>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name || o.id}
                  </option>
                ))}
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Phone (E.164)</Label>
              <Input
                className='h-8'
                placeholder='+447700900123'
                value={addPhone}
                onChange={(e) => setAddPhone(e.target.value)}
                required
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Name</Label>
              <Input className='h-8' value={addName} onChange={(e) => setAddName(e.target.value)} />
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Reason</Label>
              <Input className='h-8' value={addReason} onChange={(e) => setAddReason(e.target.value)} />
            </div>
          </div>
          <Button type='submit' size='sm' className='h-8' disabled={saving}>
            {saving ? 'Adding…' : 'Add to list'}
          </Button>
        </form>
      </Panel>

      <Panel
        title={`Opt-outs (${total})`}
        action={
          <Pill tone='neutral'>
            Page {page} of {pages} · {PAGE_SIZE} per page
          </Pill>
        }
        bodyClassName='space-y-3'
      >
        {loading ? (
          <p className='text-sm text-muted-foreground'>Loading…</p>
        ) : (
          <div className='overflow-x-auto'>
            <StripeTable>
              <TableHeader>
                <TableRow>
                  <TableHead>Phone</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Organisation</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Added</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.length === 0 ? (
                  <TableEmpty colSpan={6}>No opt-outs match these filters.</TableEmpty>
                ) : (
                  items.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>
                        <code className='text-[11px]'>{row.phone_e164 || row.phone}</code>
                      </TableCell>
                      <TableCell>{row.contact_name || row.name || '—'}</TableCell>
                      <TableCell>{row.org_name || row.org_id || '—'}</TableCell>
                      <TableCell>{row.reason || '—'}</TableCell>
                      <TableCell>{fmtDate(row.created_at)}</TableCell>
                      <TableCell>
                        <Button
                          type='button'
                          variant='destructive'
                          size='sm'
                          className='h-7 text-[11px]'
                          onClick={() => void onRemove(row.id)}
                        >
                          Remove
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </StripeTable>
          </div>
        )}
        <div className='flex gap-2'>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-8'
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-8'
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      </Panel>
    </div>
  )
}
