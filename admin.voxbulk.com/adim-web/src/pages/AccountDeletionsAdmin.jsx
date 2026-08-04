import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import { Textarea } from '@/components/ui/Textarea'
import { KpiCard } from '@/components/ui/KpiCard'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
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
import { Clock } from 'lucide-react'

function fmtWhen(v) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

function statusTone(status) {
  if (status === 'pending') return 'warning'
  if (status === 'completed') return 'success'
  return 'neutral'
}

export default function AccountDeletionsAdmin() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending')
  const [detail, setDetail] = useState(null)
  const [completeId, setCompleteId] = useState(null)
  const [confirmText, setConfirmText] = useState('')
  const [adminNotes, setAdminNotes] = useState('')

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '200', status_filter: statusFilter || 'all' })
    const res = await apiFetch(`/admin/account-deletions?${params.toString()}`)
    setRows(Array.isArray(res?.items) ? res.items : [])
  }, [statusFilter])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const pendingCount = useMemo(() => rows.filter((r) => r.status === 'pending').length, [rows])

  const openDetail = async (id) => {
    setError('')
    try {
      const data = await apiFetch(`/admin/account-deletions/${encodeURIComponent(id)}`)
      setDetail(data)
    } catch (e) {
      setError(e?.message || 'Could not load detail')
    }
  }

  const completeDeletion = async () => {
    if (!completeId) return
    if (confirmText.trim().toUpperCase() !== 'DELETE') {
      window.alert('Type DELETE to confirm')
      return
    }
    setBusy(completeId)
    setError('')
    try {
      await apiFetch(`/admin/account-deletions/${encodeURIComponent(completeId)}/complete`, {
        method: 'POST',
        body: JSON.stringify({ confirm: 'DELETE', admin_notes: adminNotes.trim() || undefined }),
      })
      setCompleteId(null)
      setConfirmText('')
      setAdminNotes('')
      setDetail(null)
      await load()
    } catch (e) {
      setError(e?.message || 'Complete failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Account deletion requests</h1>
          <p>Review user-requested account deletions, view activity, and complete archival.</p>
        </div>
        <div className='actions'>
          <Button type='button' variant='secondary' size='sm' className='h-8' onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </div>

      {error ? (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          {error}
        </div>
      ) : null}

      <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
        <KpiCard icon={Clock} label='Pending' value={pendingCount} tone='warning' index={0} />
      </div>

      <Panel title='Filters' bodyClassName='flex flex-wrap items-center gap-3'>
        <Label className='text-[12px] text-muted-foreground'>Status</Label>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className='h-8 w-[200px] text-[12px]'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='pending'>Pending</SelectItem>
            <SelectItem value='completed'>Completed</SelectItem>
            <SelectItem value='cancelled'>Cancelled</SelectItem>
            <SelectItem value='all'>All</SelectItem>
          </SelectContent>
        </Select>
      </Panel>

      <Panel title='Requests' subtitle='Open a row for activity or complete a pending deletion.' bodyClassName='overflow-x-auto'>
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Requested</TableHead>
              <TableHead>User</TableHead>
              <TableHead>Organisation</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableLoading colSpan={5} />
            ) : rows.length === 0 ? (
              <TableEmpty colSpan={5}>No deletion requests.</TableEmpty>
            ) : (
              rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{fmtWhen(row.requested_at)}</TableCell>
                  <TableCell>{row.requested_by_email}</TableCell>
                  <TableCell>
                    <div className='flex flex-col leading-tight'>
                      <span>{row.org_name || '—'}</span>
                      <span className='text-[11px] text-muted-foreground'>{row.org_id}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Pill tone={statusTone(row.status)}>{row.status}</Pill>
                  </TableCell>
                  <TableCell>
                    <div className='flex flex-wrap gap-1.5'>
                      <Button type='button' variant='secondary' size='sm' className='h-7 text-[11px]' onClick={() => openDetail(row.id)}>
                        Activity
                      </Button>
                      <Button
                        type='button'
                        variant='secondary'
                        size='sm'
                        className='h-7 text-[11px]'
                        onClick={() => {
                          localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id)
                          navigate('/organisations/all-users')
                        }}
                      >
                        OCC
                      </Button>
                      {row.status === 'pending' ? (
                        <Button
                          type='button'
                          size='sm'
                          className='h-7 text-[11px]'
                          onClick={() => {
                            setCompleteId(row.id)
                            setConfirmText('')
                            setAdminNotes('')
                          }}
                        >
                          Complete deletion
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </StripeTable>
      </Panel>

      {detail ? (
        <Panel
          title={`Activity — ${detail.requested_by_email}`}
          action={
            <Button type='button' variant='outline' size='sm' className='h-7 text-[11px]' onClick={() => setDetail(null)}>
              Close
            </Button>
          }
        >
          {(detail.activity || []).length === 0 ? (
            <p className='text-sm text-muted-foreground'>No deletion activity logged.</p>
          ) : (
            <ul className='m-0 list-none space-y-0 p-0'>
              {(detail.activity || []).map((ev) => (
                <li key={ev.id} className='border-b border-border py-2 last:border-b-0'>
                  <div className='text-sm font-semibold'>{ev.action || ev.event_type}</div>
                  <div className='text-[12px] text-muted-foreground'>
                    {[ev.actor_email, ev.detail, fmtWhen(ev.created_at)].filter(Boolean).join(' · ')}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ) : null}

      {completeId ? (
        <Panel
          title='Complete account deletion'
          subtitle='Archives the organisation, anonymizes PII, and retains invoices/audit records.'
          className='border-destructive/40'
          bodyClassName='grid max-w-md gap-3'
        >
          <p className='text-[13px] text-muted-foreground'>
            Archives the organisation, anonymizes PII, and retains invoices/audit records. Stop running campaigns first.
          </p>
          <div className='space-y-1'>
            <Label className='text-[12px]'>Admin notes (optional)</Label>
            <Textarea rows={2} value={adminNotes} onChange={(e) => setAdminNotes(e.target.value)} />
          </div>
          <div className='space-y-1'>
            <Label className='text-[12px]'>Type DELETE to confirm</Label>
            <Input className='h-8' value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          </div>
          <div className='flex gap-2'>
            <Button type='button' size='sm' className='h-8' disabled={busy === completeId} onClick={() => void completeDeletion()}>
              {busy === completeId ? 'Processing…' : 'Confirm deletion'}
            </Button>
            <Button type='button' variant='secondary' size='sm' className='h-8' onClick={() => setCompleteId(null)}>
              Cancel
            </Button>
          </div>
        </Panel>
      ) : null}
    </div>
  )
}
