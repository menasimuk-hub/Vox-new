import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
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

export default function ComplianceAudit() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const qs = filter ? `?limit=200&event_type=${encodeURIComponent(filter)}` : '?limit=200'
      const data = await apiFetch(`/admin/compliance/audit${qs}`)
      setEvents(Array.isArray(data?.events) ? data.events : [])
    } catch (e) {
      setError(e?.message || 'Could not load audit log')
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <div className='mb-1.5 text-[12px] text-muted-foreground'>
            <Link to='/compliance/consent' className='text-primary hover:underline'>
              Compliance
            </Link>{' '}
            / Audit
          </div>
          <h1>Compliance audit log</h1>
          <p>Template changes, opt-outs, send blocks, workflow launches, and retention passes.</p>
        </div>
        <div className='actions'>
          <Button type='button' variant='outline' size='sm' className='h-8' onClick={load}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          <strong>{error}</strong>
        </div>
      ) : null}

      <Panel
        title='Events'
        subtitle='Filter by event_type and review recent compliance activity.'
        action={
          <Input
            className='h-8 max-w-[280px]'
            placeholder='Filter by event_type'
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        }
        bodyClassName='overflow-x-auto'
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Org</TableHead>
              <TableHead>Order</TableHead>
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableLoading colSpan={5} />
            ) : events.length === 0 ? (
              <TableEmpty colSpan={5}>No events.</TableEmpty>
            ) : (
              events.map((ev) => (
                <TableRow key={ev.id}>
                  <TableCell>{ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}</TableCell>
                  <TableCell>
                    <code className='text-[11px]'>{ev.event_type}</code>
                  </TableCell>
                  <TableCell className='text-muted-foreground'>{ev.org_id || '—'}</TableCell>
                  <TableCell className='text-muted-foreground'>{ev.order_id || '—'}</TableCell>
                  <TableCell>
                    <pre className='m-0 whitespace-pre-wrap break-all text-[11px] text-muted-foreground'>
                      {JSON.stringify(ev.detail || {}, null, 0)}
                    </pre>
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
